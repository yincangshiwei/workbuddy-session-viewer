from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.core.settings import FC_BASE, HISTORY_BASE, MEDIA_BASE, SESSIONS_DB, TODOS_BASE
from app.services.common import decode_history_dir_name, diff_html, safe_json, ts_to_text


def build_delete_manifest(cid: str, hist_dir: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = [{"type": "db", "desc": f"sessions DB 记录: session:{cid}"}]
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
                        "filePath": m.get("filePath", ""),
                    }
                    for m in media_map.get(cid, [])
                ],

                "related": related,
                "deleteManifest": build_delete_manifest(cid, hist_dir),
            }
        )

    return result
