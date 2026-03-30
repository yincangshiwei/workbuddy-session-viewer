from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sqlite3
import time
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field



def resolve_appdata() -> Path:
    env_appdata = os.getenv("APPDATA")
    if env_appdata:
        return Path(env_appdata)
    return Path.home() / "AppData" / "Roaming"


def resolve_localappdata() -> Path:
    env_local = os.getenv("LOCALAPPDATA")
    if env_local:
        return Path(env_local)
    return Path.home() / "AppData" / "Local"


APPDATA = resolve_appdata()
LOCALAPPDATA = resolve_localappdata()
WORKBUDDY_BASE = Path(os.getenv("WORKBUDDY_BASE", APPDATA / "WorkBuddy"))
STORAGE_BASE = WORKBUDDY_BASE / "User" / "globalStorage" / "tencent-cloud.coding-copilot"
TRANSCRIPTS_BASE = Path(
    os.getenv(
        "WORKBUDDY_TRANSCRIPTS_BASE",
        LOCALAPPDATA / "WorkBuddyExtension" / "Data",
    )
)


SESSIONS_DB = Path(os.getenv("WORKBUDDY_SESSIONS_DB", WORKBUDDY_BASE / "codebuddy-sessions.vscdb"))
TODOS_BASE = Path(os.getenv("WORKBUDDY_TODOS_BASE", STORAGE_BASE / "todos"))
FC_BASE = Path(os.getenv("WORKBUDDY_FILE_CHANGES_BASE", STORAGE_BASE / "file-changes"))
HISTORY_BASE = Path(os.getenv("WORKBUDDY_HISTORY_BASE", STORAGE_BASE / "genie-history"))
MEDIA_BASE = Path(os.getenv("WORKBUDDY_MEDIA_BASE", STORAGE_BASE / "media-index"))



class DeleteRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class DeleteResponse(BaseModel):

    success: bool
    dbDeleted: int = 0
    filesDeleted: int = 0
    deletedFiles: list[str] = Field(default_factory=list)


def ts_to_text(ts: int | float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")


def safe_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def diff_html(diff_text: str) -> str:
    if not diff_text:
        return ""
    out: list[str] = []
    lines = diff_text.split("\n")
    for line in lines[:200]:
        esc = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        if line.startswith("+++") or line.startswith("---"):
            out.append(f'<span style="color:#63b3ed;font-weight:600">{esc}</span>')
        elif line.startswith("+"):
            out.append(f'<span style="color:#68d391">{esc}</span>')
        elif line.startswith("-"):
            out.append(f'<span style="color:#fc8181">{esc}</span>')
        elif line.startswith("@@"):
            out.append(f'<span style="color:#f6ad55">{esc}</span>')
        else:
            out.append(f'<span style="color:#a0aec0">{esc}</span>')
    if len(lines) > 200:
        out.append(f'<span style="color:#718096">... 还有 {len(lines)-200} 行 ...</span>')
    return "\n".join(out)


def decode_history_dir_name(name: str) -> str:
    try:
        b64 = name.replace("_", "/").replace("-", "+")
        while len(b64) % 4:
            b64 += "="
        return base64.b64decode(b64).decode("utf-8", errors="replace").rstrip("\x00").rstrip("?")
    except Exception:
        return ""


def build_delete_manifest(cid: str, hist_dir: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = [
        {"type": "db", "desc": f"sessions DB 记录: session:{cid}"}
    ]
    todo_file = TODOS_BASE / f"{cid}.json"
    if todo_file.exists():
        items.append({"type": "file", "desc": f"todos/{cid}.json"})

    fc_dir = FC_BASE / cid
    if fc_dir.is_dir():
        items.append({"type": "dir", "desc": f"file-changes/{cid}/"})

    if hist_dir:
        conv_dir = HISTORY_BASE / hist_dir / "conversations" / cid
        if conv_dir.is_dir():
            items.append({"type": "dir", "desc": f"genie-history/.../conversations/{cid}/"})

    return items


def resolve_transcript_index(cid: str) -> Path | None:
    if not cid or not TRANSCRIPTS_BASE.exists():
        return None

    candidates: list[tuple[int, Path]] = []
    try:
        for p in TRANSCRIPTS_BASE.rglob("index.json"):
            if p.parent.name != cid:
                continue

            s = str(p).replace("\\", "/").lower()
            score = 0
            if "/history/" in s:
                score += 20
            if "/check-point/" in s or "/checkpoint/" in s:
                score -= 10

            msg_dir = p.parent / "messages"
            if msg_dir.is_dir():
                score += 10
                try:
                    if next(msg_dir.glob("*.json"), None):
                        score += 5
                except Exception:
                    pass

            candidates.append((score, p))
    except Exception:
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], -len(str(x[1]))), reverse=True)
    return candidates[0][1]



def json_pretty(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def parse_message_content(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    chunks: list[str] = []
    tool_events: list[dict[str, Any]] = []

    for block in blocks:
        btype = str(block.get("type", ""))
        if btype == "text":
            text = str(block.get("text", "")).strip()
            if text:
                chunks.append(text)
            continue

        if btype == "tool-call":
            tool_name = str(block.get("toolName", ""))
            tool_call_id = str(block.get("toolCallId", ""))
            args = block.get("args")
            tool_events.append(
                {
                    "type": btype,
                    "toolName": tool_name,
                    "toolCallId": tool_call_id,
                    "args": args,
                }
            )
            continue

        if btype == "tool-result":
            tool_name = str(block.get("toolName", ""))
            tool_call_id = str(block.get("toolCallId", ""))
            result = block.get("result")
            is_error = bool(block.get("isError", False))
            tool_events.append(
                {
                    "type": btype,
                    "toolName": tool_name,
                    "toolCallId": tool_call_id,
                    "result": result,
                    "isError": is_error,
                }
            )
            continue


        if btype:
            chunks.append(f"[{btype}]")

    return {
        "text": "\n\n".join(x for x in chunks if x).strip(),
        "toolEvents": tool_events,
    }



def load_conversation_chat(cid: str) -> dict[str, Any]:
    idx = resolve_transcript_index(cid)
    if not idx:
        raise HTTPException(status_code=404, detail="chat transcript not found")

    data = safe_json(idx)
    if not data:
        raise HTTPException(status_code=500, detail="invalid transcript index")

    msg_dir = idx.parent / "messages"
    out_messages: list[dict[str, Any]] = []
    for meta in data.get("messages", []):
        mid = str(meta.get("id", ""))
        role = str(meta.get("role", ""))
        mtype = str(meta.get("type", ""))
        msg_file = msg_dir / f"{mid}.json" if mid else None
        created_at_ts = 0
        if msg_file and msg_file.exists():
            try:
                created_at_ts = int(msg_file.stat().st_ctime * 1000)
            except Exception:
                created_at_ts = 0

        item: dict[str, Any] = {
            "id": mid,
            "role": role,
            "type": mtype,
            "isComplete": bool(meta.get("isComplete", False)),
            "text": "",
            "toolEvents": [],
            "createdAtTs": created_at_ts,
            "createdAt": ts_to_text(created_at_ts),
            "messagePath": str(msg_file) if msg_file else "",
            "raw": None,
        }

        if mid and msg_file:
            raw = safe_json(msg_file)
            if raw and isinstance(raw.get("message"), str):
                try:
                    msg_obj = json.loads(raw["message"])
                    item["raw"] = msg_obj
                    content = msg_obj.get("content", [])
                    if isinstance(content, list):
                        parsed = parse_message_content(content)
                        item["text"] = parsed.get("text", "")
                        item["toolEvents"] = parsed.get("toolEvents", [])
                except Exception:
                    item["text"] = raw["message"]

        out_messages.append(item)


    return {
        "conversationId": cid,
        "indexPath": str(idx),
        "messageCount": len(out_messages),
        "messages": out_messages,
        "requests": data.get("requests", []),
    }


def load_sessions() -> list[dict[str, Any]]:

    if not SESSIONS_DB.exists():
        return []

    conn = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute("SELECT value FROM ItemTable")
    rows = cur.fetchall()
    conn.close()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        try:
            sessions.append(json.loads(row[0]))
        except Exception:
            continue

    sessions.sort(key=lambda s: s.get("createdAt", 0), reverse=True)
    cwd_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        cwd_groups[s.get("cwd", "")].append(s)

    todos_map: dict[str, list[dict[str, Any]]] = {}
    if TODOS_BASE.exists():
        for f in TODOS_BASE.glob("*.json"):
            data = safe_json(f)
            if data:
                todos_map[f.stem] = data.get("todos", [])

    fc_map: dict[str, list[dict[str, Any]]] = {}
    if FC_BASE.exists():
        for cid_dir in FC_BASE.iterdir():
            if not cid_dir.is_dir():
                continue
            changes: list[dict[str, Any]] = []
            for fc_file in cid_dir.glob("*.json"):
                data = safe_json(fc_file)
                if not data:
                    continue
                changes.append(
                    {
                        "fileName": data.get("fileName", fc_file.name),
                        "filePath": data.get("filePath", ""),
                        "changeType": data.get("changeType", ""),
                        "addedLines": data.get("addedLines", 0),
                        "removedLines": data.get("removedLines", 0),
                        "diff": data.get("diff", ""),
                        "timestamp": data.get("timestamp", 0),
                    }
                )
            if changes:
                fc_map[cid_dir.name] = sorted(changes, key=lambda x: x.get("timestamp", 0))

    media_map: dict[str, list[dict[str, Any]]] = {}
    if MEDIA_BASE.exists():
        for mf in MEDIA_BASE.glob("*.json"):
            data = safe_json(mf)
            if not data:
                continue
            for rec in data.get("records", {}).values():
                sid = rec.get("sessionId", "")
                if sid:
                    media_map.setdefault(sid, []).append(rec)

    hist_dir_map: dict[str, str] = {}
    if HISTORY_BASE.exists():
        for d in HISTORY_BASE.iterdir():
            if not d.is_dir():
                continue
            cwd = decode_history_dir_name(d.name)
            if cwd:
                hist_dir_map[cwd] = d.name

    result: list[dict[str, Any]] = []
    for s in sessions:
        cid = s.get("conversationId", "")
        cwd = s.get("cwd", "")
        file_changes = fc_map.get(cid, [])

        related = []
        for x in cwd_groups.get(cwd, []):
            rid = x.get("conversationId", "")
            if rid == cid:
                continue
            related.append(
                {
                    "conversationId": rid,
                    "title": x.get("title", ""),
                    "status": x.get("status", ""),
                    "createdAt": ts_to_text(x.get("createdAt", 0)),
                    "updatedAt": ts_to_text(x.get("updatedAt", 0)),
                    "todos": todos_map.get(rid, []),
                    "fileChanges": [
                        {
                            "fileName": fc.get("fileName", ""),
                            "changeType": fc.get("changeType", ""),
                            "addedLines": fc.get("addedLines", 0),
                            "removedLines": fc.get("removedLines", 0),
                        }
                        for fc in fc_map.get(rid, [])
                    ],
                }
            )

        hist_dir = hist_dir_map.get(cwd, "")
        result.append(
            {
                "conversationId": cid,
                "title": s.get("title", ""),
                "status": s.get("status", ""),
                "cwd": cwd,
                "createdAtTs": s.get("createdAt", 0),
                "updatedAtTs": s.get("updatedAt", 0),
                "createdAt": ts_to_text(s.get("createdAt", 0)),
                "updatedAt": ts_to_text(s.get("updatedAt", 0)),
                "cwdExists": Path(cwd).exists() if cwd else False,
                "todos": todos_map.get(cid, []),
                "fileChanges": [
                    {
                        **fc,
                        "timestampText": ts_to_text(fc.get("timestamp", 0)),
                        "diffHtml": diff_html(fc.get("diff", "")),
                    }
                    for fc in file_changes
                ],
                "mediaFiles": [
                    {
                        "fileName": m.get("fileName", ""),
                        "mimeType": m.get("mimeType", ""),
                        "size": m.get("size", 0),
                    }
                    for m in media_map.get(cid, [])
                ],
                "related": related,
                "deleteManifest": build_delete_manifest(cid, hist_dir),
            }
        )

    return result


def load_session_values(ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids or not SESSIONS_DB.exists():
        return {}

    out: dict[str, dict[str, Any]] = {}
    conn = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True)
    cur = conn.cursor()
    for cid in ids:
        key = f"session:{cid}"
        cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
        row = cur.fetchone()
        if not row:
            continue
        try:
            obj = json.loads(row[0])
            if isinstance(obj, dict):
                out[cid] = obj
        except Exception:
            continue
    conn.close()
    return out


def collect_media_records(cid: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not MEDIA_BASE.exists():
        return records
    for mf in MEDIA_BASE.glob("*.json"):
        data = safe_json(mf)
        if not data:
            continue
        for rec in data.get("records", {}).values():
            if rec.get("sessionId") == cid:
                records.append(rec)
    return records


def build_export_zip(ids: list[str]) -> bytes:
    uniq_ids = [x for x in dict.fromkeys(ids) if x]
    session_map = load_session_values(uniq_ids)

    buf = io.BytesIO()
    exported: list[dict[str, Any]] = []

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cid in uniq_ids:
            session = session_map.get(cid)
            if not session:
                continue

            root = f"sessions/{cid}"
            zf.writestr(
                f"{root}/session.json",
                json.dumps(session, ensure_ascii=False, indent=2),
            )

            todo_file = TODOS_BASE / f"{cid}.json"
            if todo_file.exists():
                zf.writestr(f"{root}/todos.json", todo_file.read_text(encoding="utf-8"))

            fc_dir = FC_BASE / cid
            if fc_dir.is_dir():
                for fc in fc_dir.glob("*.json"):
                    zf.writestr(
                        f"{root}/file-changes/{fc.name}",
                        fc.read_text(encoding="utf-8"),
                    )

            media_records = collect_media_records(cid)
            if media_records:
                zf.writestr(
                    f"{root}/media-records.json",
                    json.dumps(media_records, ensure_ascii=False, indent=2),
                )

            idx = resolve_transcript_index(cid)
            transcript_ok = False
            if idx and idx.exists():
                transcript_ok = True
                zf.writestr(
                    f"{root}/transcript/index.json",
                    idx.read_text(encoding="utf-8"),
                )
                msg_dir = idx.parent / "messages"
                if msg_dir.is_dir():
                    for mf in msg_dir.glob("*.json"):
                        zf.writestr(
                            f"{root}/transcript/messages/{mf.name}",
                            mf.read_text(encoding="utf-8"),
                        )

            exported.append(
                {
                    "conversationId": cid,
                    "title": session.get("title", ""),
                    "transcriptIncluded": transcript_ok,
                }
            )

        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "workbuddy-session-export-v1",
                    "exportedAt": int(time.time() * 1000),
                    "count": len(exported),
                    "sessions": exported,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    return buf.getvalue()


def import_from_zip(blob: bytes) -> dict[str, Any]:
    if not SESSIONS_DB.exists():
        raise HTTPException(status_code=500, detail="sessions DB not found")

    batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
    imported_items: list[dict[str, Any]] = []

    TODOS_BASE.mkdir(parents=True, exist_ok=True)
    FC_BASE.mkdir(parents=True, exist_ok=True)
    MEDIA_BASE.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(SESSIONS_DB))
    cur = conn.cursor()

    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = set(zf.namelist())
        session_ids = sorted(
            {
                p.split("/")[1]
                for p in names
                if p.startswith("sessions/") and p.count("/") >= 2
            }
        )

        for old_cid in session_ids:
            root = f"sessions/{old_cid}"
            session_key = f"{root}/session.json"
            if session_key not in names:
                continue

            try:
                session_obj = json.loads(zf.read(session_key).decode("utf-8"))
            except Exception:
                continue
            if not isinstance(session_obj, dict):
                continue

            new_cid = uuid.uuid4().hex
            session_obj["conversationId"] = new_cid
            now_ms = int(time.time() * 1000)
            session_obj["updatedAt"] = now_ms

            cur.execute(
                "INSERT INTO ItemTable(key,value) VALUES(?,?)",
                (
                    f"session:{new_cid}",
                    json.dumps(session_obj, ensure_ascii=False),
                ),
            )

            todo_key = f"{root}/todos.json"
            if todo_key in names:
                try:
                    todo_obj = json.loads(zf.read(todo_key).decode("utf-8"))
                    if isinstance(todo_obj, dict):
                        (TODOS_BASE / f"{new_cid}.json").write_text(
                            json.dumps(todo_obj, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                except Exception:
                    pass

            fc_names = [
                n for n in names if n.startswith(f"{root}/file-changes/") and n.endswith(".json")
            ]
            if fc_names:
                dest_fc = FC_BASE / new_cid
                dest_fc.mkdir(parents=True, exist_ok=True)
                for fn in fc_names:
                    try:
                        content = zf.read(fn).decode("utf-8")
                        (dest_fc / Path(fn).name).write_text(content, encoding="utf-8")
                    except Exception:
                        continue

            media_key = f"{root}/media-records.json"
            if media_key in names:
                try:
                    media_list = json.loads(zf.read(media_key).decode("utf-8"))
                    if isinstance(media_list, list) and media_list:
                        media_out: dict[str, Any] = {"records": {}}
                        for rec in media_list:
                            if not isinstance(rec, dict):
                                continue
                            copied = dict(rec)
                            copied["sessionId"] = new_cid
                            media_out["records"][uuid.uuid4().hex] = copied
                        if media_out["records"]:
                            (MEDIA_BASE / f"import-{new_cid}.json").write_text(
                                json.dumps(media_out, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                except Exception:
                    pass

            t_idx_key = f"{root}/transcript/index.json"
            t_msg_prefix = f"{root}/transcript/messages/"
            if t_idx_key in names:
                try:
                    t_root = TRANSCRIPTS_BASE / "history" / "imported" / batch_id / new_cid
                    t_msg_dir = t_root / "messages"
                    t_msg_dir.mkdir(parents=True, exist_ok=True)
                    t_index_obj = json.loads(zf.read(t_idx_key).decode("utf-8"))
                    if isinstance(t_index_obj, dict):
                        (t_root / "index.json").write_text(
                            json.dumps(t_index_obj, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    for n in names:
                        if n.startswith(t_msg_prefix) and n.endswith(".json"):
                            (t_msg_dir / Path(n).name).write_text(
                                zf.read(n).decode("utf-8"),
                                encoding="utf-8",
                            )
                except Exception:
                    pass

            imported_items.append(
                {
                    "oldConversationId": old_cid,
                    "newConversationId": new_cid,
                    "title": session_obj.get("title", ""),
                }
            )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "count": len(imported_items),
        "items": imported_items,
    }


def delete_sessions(ids: list[str]) -> int:

    if not SESSIONS_DB.exists():
        return 0
    conn = sqlite3.connect(str(SESSIONS_DB))
    cur = conn.cursor()
    deleted = 0
    for cid in ids:
        cur.execute("DELETE FROM ItemTable WHERE key=?", (f"session:{cid}",))
        deleted += cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_local_files(ids: list[str]) -> list[str]:
    deleted: list[str] = []
    for cid in ids:
        todo_file = TODOS_BASE / f"{cid}.json"
        if todo_file.exists():
            todo_file.unlink(missing_ok=True)
            deleted.append(str(todo_file))

        fc_dir = FC_BASE / cid
        if fc_dir.exists():
            shutil.rmtree(fc_dir, ignore_errors=True)
            deleted.append(str(fc_dir))

        if HISTORY_BASE.exists():
            for conv_dir in HISTORY_BASE.glob(f"*/conversations/{cid}"):
                shutil.rmtree(conv_dir, ignore_errors=True)
                deleted.append(str(conv_dir))

    return deleted


app = FastAPI(title="WorkBuddy Session Viewer API")

allow_origins = os.getenv("ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in allow_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sessions")
def get_sessions() -> dict[str, Any]:
    sessions = load_sessions()
    return {"total": len(sessions), "sessions": sessions}


@app.get("/api/session/{cid}/chat")
def get_session_chat(cid: str) -> dict[str, Any]:
    if not cid:
        raise HTTPException(status_code=400, detail="cid required")
    return load_conversation_chat(cid)


@app.post("/api/export")
def export_api(payload: ExportRequest) -> StreamingResponse:
    ids = [x for x in payload.ids if x]
    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    blob = build_export_zip(ids)
    file_name = f"workbuddy-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@app.post("/api/import")
async def import_api(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file required")

    try:
        content = await file.read()
        result = import_from_zip(content)
        return result
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="invalid zip file") from e


@app.post("/api/delete", response_model=DeleteResponse)
def delete_api(payload: DeleteRequest) -> DeleteResponse:


    ids = [x for x in payload.ids if x]
    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    db_deleted = delete_sessions(ids)
    deleted_files = delete_local_files(ids)
    return DeleteResponse(
        success=True,
        dbDeleted=db_deleted,
        filesDeleted=len(deleted_files),
        deletedFiles=deleted_files,
    )


static_dir = (Path(__file__).resolve().parents[1] / "static").resolve()
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
