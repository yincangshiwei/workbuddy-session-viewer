from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, HTTPException

from app.core.settings import SESSIONS_DB
from app.schemas.session import RestoreRequest, RestoreResponse

router = APIRouter()


def restore_sessions(ids: list[str]) -> int:
    """清除逻辑删除标记（从 JSON 中彻底删除 deletedAt 字段，与正常会话保持一致）"""
    if not SESSIONS_DB.exists():
        return 0
    conn = sqlite3.connect(str(SESSIONS_DB))
    cur = conn.cursor()
    restored = 0
    for cid in ids:
        key = f"session:{cid}"
        cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,))
        row = cur.fetchone()
        if not row:
            continue
        try:
            data = json.loads(row[0])
        except Exception:
            continue
        if "deletedAt" not in data:
            continue
        del data["deletedAt"]
        cur.execute("UPDATE ItemTable SET value=? WHERE key=?", (json.dumps(data, ensure_ascii=False), key))
        restored += cur.rowcount
    conn.commit()
    conn.close()
    return restored


@router.post("/restore", response_model=RestoreResponse)
def restore_api(payload: RestoreRequest) -> RestoreResponse:
    ids = [x for x in payload.ids if x]
    if not ids:
        raise HTTPException(status_code=400, detail="ids required")
    restored = restore_sessions(ids)
    return RestoreResponse(success=True, restored=restored)
