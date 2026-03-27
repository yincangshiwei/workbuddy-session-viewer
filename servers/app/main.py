from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


def resolve_appdata() -> Path:
    env_appdata = os.getenv("APPDATA")
    if env_appdata:
        return Path(env_appdata)
    return Path.home() / "AppData" / "Roaming"


APPDATA = resolve_appdata()
WORKBUDDY_BASE = Path(os.getenv("WORKBUDDY_BASE", APPDATA / "WorkBuddy"))
STORAGE_BASE = WORKBUDDY_BASE / "User" / "globalStorage" / "tencent-cloud.coding-copilot"


SESSIONS_DB = Path(os.getenv("WORKBUDDY_SESSIONS_DB", WORKBUDDY_BASE / "codebuddy-sessions.vscdb"))
TODOS_BASE = Path(os.getenv("WORKBUDDY_TODOS_BASE", STORAGE_BASE / "todos"))
FC_BASE = Path(os.getenv("WORKBUDDY_FILE_CHANGES_BASE", STORAGE_BASE / "file-changes"))
HISTORY_BASE = Path(os.getenv("WORKBUDDY_HISTORY_BASE", STORAGE_BASE / "genie-history"))
MEDIA_BASE = Path(os.getenv("WORKBUDDY_MEDIA_BASE", STORAGE_BASE / "media-index"))


class DeleteRequest(BaseModel):
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
