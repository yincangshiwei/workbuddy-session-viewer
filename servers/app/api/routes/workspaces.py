from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.settings import FC_BASE, HISTORY_BASE, SESSIONS_DB, TODOS_BASE
from app.schemas.session import WorkspaceDeleteRequest

router = APIRouter()


@router.get("/workspaces")
def get_workspaces() -> dict[str, Any]:
    """按工作目录聚合会话，返回工作空间列表"""
    if not SESSIONS_DB.exists():
        return {"total": 0, "workspaces": []}

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

    cwd_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        cwd = s.get("cwd", "")
        if cwd:
            cwd_groups[cwd].append(s)

    workspaces: list[dict[str, Any]] = []
    for cwd, group in cwd_groups.items():
        # 活跃会话：DB 中仍存在记录（无论是否逻辑删除），均算"有关联"
        # 仅用于显示区分：正常 vs 逻辑删除
        normal_sessions = [s for s in group if not s.get("deletedAt")]
        soft_deleted_sessions = [s for s in group if s.get("deletedAt")]
        # 只有 DB 中该 cwd 下所有记录都被后台彻底删除（即不存在任何记录）才可删除目录
        # 此处 group 非空说明 DB 中还有记录，不可删除
        can_delete = len(group) == 0
        workspaces.append({
            "cwd": cwd,
            "cwdExists": Path(cwd).exists() if cwd else False,
            "totalSessions": len(group),
            "activeSessions": len(normal_sessions),
            "deletedSessions": len(soft_deleted_sessions),
            "canDelete": can_delete,
            "sessions": [
                {
                    "conversationId": s.get("conversationId", ""),
                    "title": s.get("title", ""),
                    "status": s.get("status", ""),
                    "createdAt": s.get("createdAt", 0),
                    "updatedAt": s.get("updatedAt", 0),
                    "deletedAt": s.get("deletedAt", 0) or 0,
                    "isDeleted": bool(s.get("deletedAt")),
                }
                for s in sorted(group, key=lambda x: x.get("createdAt", 0), reverse=True)
            ],
        })

    workspaces.sort(key=lambda w: w["activeSessions"], reverse=True)
    return {"total": len(workspaces), "workspaces": workspaces}


@router.delete("/workspace")
def delete_workspace(payload: WorkspaceDeleteRequest) -> dict[str, Any]:
    """删除工作目录（仅允许没有关联活跃会话的工作目录）"""
    cwd = payload.cwd.strip()
    if not cwd:
        raise HTTPException(status_code=400, detail="工作目录路径不能为空")

    cwd_path = Path(cwd)
    if not cwd_path.exists():
        raise HTTPException(status_code=404, detail="工作目录不存在")

    # 检查是否有关联的活跃会话
    if SESSIONS_DB.exists():
        conn = sqlite3.connect(f"file:{SESSIONS_DB}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT value FROM ItemTable")
        rows = cur.fetchall()
        conn.close()

        for row in rows:
            try:
                data = json.loads(row[0])
            except Exception:
                continue
            if data.get("cwd") == cwd:
                # DB 中仍有该 cwd 的记录（无论是否逻辑删除），均不允许删除目录
                raise HTTPException(
                    status_code=400,
                    detail="该工作目录下仍有会话记录（包括逻辑删除的），无法删除。请先在后台彻底删除所有关联会话。",
                )

    # 删除工作目录
    try:
        shutil.rmtree(cwd_path, ignore_errors=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除工作目录失败: {e}")

    return {"success": True, "deletedPath": cwd}
