from __future__ import annotations

import shutil
import sqlite3

from app.core.settings import FC_BASE, HISTORY_BASE, SESSIONS_DB, TODOS_BASE


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
