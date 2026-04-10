from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, HTTPException

from app.core.settings import SESSIONS_DB
from app.schemas.session import UpdateTitleRequest

router = APIRouter()


@router.put("/session/{conversation_id}/title")
def update_title(conversation_id: str, payload: UpdateTitleRequest) -> dict:
    new_title = payload.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="标题不能为空")

    if not SESSIONS_DB.exists():
        raise HTTPException(status_code=500, detail="数据库文件不存在")

    conn = sqlite3.connect(str(SESSIONS_DB))
    cur = conn.cursor()
    key = f"session:{conversation_id}"
    cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        data = json.loads(row[0])
    except Exception:
        conn.close()
        raise HTTPException(status_code=500, detail="会话数据解析失败")

    data["title"] = new_title
    cur.execute("UPDATE ItemTable SET value=? WHERE key=?", (json.dumps(data, ensure_ascii=False), key))
    conn.commit()
    conn.close()
    return {"success": True, "title": new_title}
