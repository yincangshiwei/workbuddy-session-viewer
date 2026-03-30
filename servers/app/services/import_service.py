from __future__ import annotations

import io
import json
import sqlite3
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.settings import FC_BASE, MEDIA_BASE, SESSIONS_DB, TODOS_BASE, TRANSCRIPTS_BASE


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
        session_ids = sorted({p.split("/")[1] for p in names if p.startswith("sessions/") and p.count("/") >= 2})

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

            fc_names = [n for n in names if n.startswith(f"{root}/file-changes/") and n.endswith(".json")]
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
