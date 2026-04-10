from __future__ import annotations

"""
监控同步状态数据库（SQLite）

表结构 monitor_messages：
  id              TEXT  PRIMARY KEY  -- conversationId + ":" + messageId
  conversation_id TEXT  NOT NULL
  message_id      TEXT  NOT NULL
  role            TEXT  NOT NULL
  fingerprint     TEXT  NOT NULL     -- MD5(role+text+toolEvents+isComplete)
  synced          INTEGER NOT NULL DEFAULT 0  -- 0=未同步 1=已同步
  synced_at       TEXT               -- 同步时间（ISO格式）
  created_at      TEXT  NOT NULL     -- 消息创建时间
  updated_at      TEXT  NOT NULL     -- 记录最后更新时间

初始化操作：清空表，重新从会话数据填充，状态全部置为未同步(0)
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

# DB 文件放在 servers/ 目录下
_DB_PATH = Path(__file__).resolve().parents[2] / "monitor_sync.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """建表（幂等）"""
    with _lock:
        conn = _get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_messages (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_id      TEXT NOT NULL,
                role            TEXT NOT NULL,
                fingerprint     TEXT NOT NULL,
                synced          INTEGER NOT NULL DEFAULT 0,
                synced_at       TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv ON monitor_messages(conversation_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_synced ON monitor_messages(synced)")
        conn.commit()
        conn.close()


def reset_all(messages: list[dict[str, Any]]) -> int:
    """
    初始化：清空全表，重新写入所有消息，状态置为未同步。
    messages: [{conversation_id, message_id, role, fingerprint, created_at}, ...]
    返回写入条数。
    """
    now = _now()
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM monitor_messages")
        rows = []
        for m in messages:
            pk = f"{m['conversation_id']}:{m['message_id']}"
            rows.append((
                pk,
                m["conversation_id"],
                m["message_id"],
                m.get("role", ""),
                m.get("fingerprint", ""),
                0,       # synced = 未同步
                None,    # synced_at
                m.get("created_at", now),
                now,
            ))
        conn.executemany(
            "INSERT OR REPLACE INTO monitor_messages "
            "(id, conversation_id, message_id, role, fingerprint, synced, synced_at, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM monitor_messages").fetchone()[0]
        conn.close()
    return count


def upsert_messages(messages: list[dict[str, Any]]) -> dict[str, list[str]]:
    """
    增量更新：
    - 新消息：插入，synced=0
    - 已有且指纹变化：更新 fingerprint，synced=0（需重新同步）
    - 已有且指纹不变：不做任何操作
    返回 {new: [pk], changed: [pk], unchanged: [pk]}
    """
    now = _now()
    result: dict[str, list[str]] = {"new": [], "changed": [], "unchanged": []}

    with _lock:
        conn = _get_conn()
        for m in messages:
            pk = f"{m['conversation_id']}:{m['message_id']}"
            row = conn.execute(
                "SELECT fingerprint, synced FROM monitor_messages WHERE id=?", (pk,)
            ).fetchone()

            if row is None:
                conn.execute(
                    "INSERT INTO monitor_messages "
                    "(id, conversation_id, message_id, role, fingerprint, synced, synced_at, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,0,NULL,?,?)",
                    (pk, m["conversation_id"], m["message_id"],
                     m.get("role", ""), m.get("fingerprint", ""),
                     m.get("created_at", now), now),
                )
                result["new"].append(pk)
            elif row["fingerprint"] != m.get("fingerprint", ""):
                conn.execute(
                    "UPDATE monitor_messages SET fingerprint=?, synced=0, synced_at=NULL, updated_at=? WHERE id=?",
                    (m.get("fingerprint", ""), now, pk),
                )
                result["changed"].append(pk)
            else:
                result["unchanged"].append(pk)

        conn.commit()
        conn.close()

    return result


def get_unsynced(conversation_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    """获取未同步的消息记录（synced=0）"""
    with _lock:
        conn = _get_conn()
        if conversation_id:
            rows = conn.execute(
                "SELECT * FROM monitor_messages WHERE synced=0 AND conversation_id=? LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM monitor_messages WHERE synced=0 LIMIT ?",
                (limit,),
            ).fetchall()
        result = [dict(r) for r in rows]
        conn.close()
    return result


def mark_synced(pks: list[str]) -> None:
    """将指定记录标记为已同步"""
    if not pks:
        return
    now = _now()
    with _lock:
        conn = _get_conn()
        conn.executemany(
            "UPDATE monitor_messages SET synced=1, synced_at=? WHERE id=?",
            [(now, pk) for pk in pks],
        )
        conn.commit()
        conn.close()


def get_stats() -> dict[str, Any]:
    """返回同步状态统计"""
    with _lock:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM monitor_messages").fetchone()[0]
        synced = conn.execute("SELECT COUNT(*) FROM monitor_messages WHERE synced=1").fetchone()[0]
        unsynced = conn.execute("SELECT COUNT(*) FROM monitor_messages WHERE synced=0").fetchone()[0]
        conversations = conn.execute(
            "SELECT COUNT(DISTINCT conversation_id) FROM monitor_messages"
        ).fetchone()[0]
        conn.close()
    return {
        "total": total,
        "synced": synced,
        "unsynced": unsynced,
        "conversations": conversations,
        "db_path": str(_DB_PATH),
    }


def get_messages_page(
    conversation_id: str | None = None,
    synced: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """分页查询消息记录"""
    offset = (page - 1) * page_size
    conditions = []
    params: list[Any] = []
    if conversation_id:
        conditions.append("conversation_id=?")
        params.append(conversation_id)
    if synced is not None:
        conditions.append("synced=?")
        params.append(synced)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _lock:
        conn = _get_conn()
        total = conn.execute(
            f"SELECT COUNT(*) FROM monitor_messages {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM monitor_messages {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        result = [dict(r) for r in rows]
        conn.close()

    return {"total": total, "page": page, "page_size": page_size, "rows": result}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

