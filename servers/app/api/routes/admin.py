from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Any

from app.core.admin_state import is_admin_mode
from app.core.monitor_config import load_config, save_config
from app.core.monitor_db import get_messages_page
from app.services.monitor_service import (
    collect_machine_info,
    get_sync_stats,
    get_upload_errors,
    initialize_sync,
    poll_and_upload,
    refresh_machine_info,
    upload_unsynced,
)

router = APIRouter(prefix="/admin")


def require_admin():
    if not is_admin_mode():
        raise HTTPException(status_code=403, detail="需要管理员模式启动才能访问此接口")


# ── 管理模式状态 ──────────────────────────────────────────────
@router.get("/status")
def get_admin_status():
    """返回当前是否为管理员模式（前端判断用，无需鉴权）"""
    return {"admin": is_admin_mode()}


# ── 监控上传配置 ──────────────────────────────────────────────
@router.get("/monitor/config", dependencies=[Depends(require_admin)])
def get_monitor_config():
    return load_config()


class MonitorConfigIn(BaseModel):
    enabled: bool = False
    protocol: str = "https"
    url: str = ""
    headers: dict[str, str] = {}
    include_basic: bool = True
    include_full: bool = False
    include_user: bool = True
    include_assistant: bool = False
    batch_size: int = 50
    retry_times: int = 3


@router.post("/monitor/config", dependencies=[Depends(require_admin)])
def update_monitor_config(body: MonitorConfigIn):
    saved = save_config(body.model_dump())
    return {"success": True, "config": saved}


# ── 初始化同步数据 ────────────────────────────────────────────
@router.post("/monitor/initialize", dependencies=[Depends(require_admin)])
def initialize_monitor():
    """
    初始化同步数据库：
    清空全部记录，重新从所有活跃会话读取消息，状态全部置为"未同步"。
    换服务地址或需要重置时调用此接口。
    """
    result = initialize_sync()
    return result


# ── 同步状态统计 ──────────────────────────────────────────────
@router.get("/monitor/stats", dependencies=[Depends(require_admin)])
def get_monitor_stats():
    """返回 DB 中消息的同步状态统计"""
    return get_sync_stats()


# ── 分页查询消息记录 ──────────────────────────────────────────
@router.get("/monitor/messages", dependencies=[Depends(require_admin)])
def list_monitor_messages(
    conversation_id: str | None = Query(None),
    synced: int | None = Query(None, description="0=未同步 1=已同步 不传=全部"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return get_messages_page(
        conversation_id=conversation_id,
        synced=synced,
        page=page,
        page_size=page_size,
    )


# ── 手动触发上传（上传所有未同步记录）────────────────────────
@router.post("/monitor/upload", dependencies=[Depends(require_admin)])
def trigger_upload(conversation_id: str | None = None):
    """上传所有未同步记录，或指定会话的未同步记录"""
    return upload_unsynced(conversation_id=conversation_id)


# ── 完整轮询（扫描变化 + 上传）───────────────────────────────
@router.post("/monitor/poll", dependencies=[Depends(require_admin)])
def trigger_poll():
    """执行一次完整轮询：扫描所有活跃会话变化 + 上传未同步记录"""
    return poll_and_upload()


# ── 上传错误日志 ──────────────────────────────────────────────
@router.get("/monitor/errors", dependencies=[Depends(require_admin)])
def get_monitor_errors():
    return {"errors": get_upload_errors()}


# ── 本机环境信息 ──────────────────────────────────────────────
@router.get("/machine-info", dependencies=[Depends(require_admin)])
def get_machine_info():
    return collect_machine_info()


@router.post("/machine-info/refresh", dependencies=[Depends(require_admin)])
def refresh_machine_info_api():
    return refresh_machine_info()
