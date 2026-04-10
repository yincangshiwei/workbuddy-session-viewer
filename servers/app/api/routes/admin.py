from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from app.core.admin_state import is_admin_mode
from app.core.monitor_config import load_config, save_config
from app.services.monitor_service import (
    check_and_upload,
    clear_cache,
    collect_machine_info,
    get_cache_stats,
    get_upload_errors,
    refresh_machine_info,
)

router = APIRouter(prefix="/admin")


def require_admin():
    if not is_admin_mode():
        raise HTTPException(status_code=403, detail="需要管理员模式启动才能访问此接口")


# ── 管理模式状态 ──────────────────────────────────────────────
@router.get("/status")
def get_admin_status():
    """返回当前是否为管理员模式（前端用于判断是否显示管理菜单）"""
    return {"admin": is_admin_mode()}


# ── 监控上传配置 ──────────────────────────────────────────────
@router.get("/monitor/config", dependencies=[Depends(require_admin)])
def get_monitor_config():
    return load_config()


class MonitorConfigIn(BaseModel):
    enabled: bool = False
    protocol: str = "http"
    url: str = ""
    headers: dict[str, str] = {}
    include_basic: bool = True
    include_full: bool = False
    include_user: bool = True
    include_assistant: bool = True
    batch_size: int = 50
    retry_times: int = 3


@router.post("/monitor/config", dependencies=[Depends(require_admin)])
def update_monitor_config(body: MonitorConfigIn):
    saved = save_config(body.model_dump())
    return {"success": True, "config": saved}


# ── 手动触发上传 ──────────────────────────────────────────────
class UploadTriggerIn(BaseModel):
    conversationId: str


@router.post("/monitor/upload", dependencies=[Depends(require_admin)])
def trigger_upload(body: UploadTriggerIn):
    result = check_and_upload(body.conversationId)
    return result


# ── 批量触发上传 ──────────────────────────────────────────────
class BatchUploadIn(BaseModel):
    conversationIds: list[str]


@router.post("/monitor/upload-batch", dependencies=[Depends(require_admin)])
def trigger_batch_upload(body: BatchUploadIn):
    results = {}
    for cid in body.conversationIds:
        results[cid] = check_and_upload(cid)
    return {"results": results}


# ── 缓存管理 ──────────────────────────────────────────────────
@router.get("/monitor/cache-stats", dependencies=[Depends(require_admin)])
def get_monitor_cache_stats():
    return get_cache_stats()


@router.post("/monitor/clear-cache", dependencies=[Depends(require_admin)])
def clear_monitor_cache(conversationId: str | None = None):
    clear_cache(conversationId)
    return {"success": True}


# ── 上传错误日志 ──────────────────────────────────────────────
@router.get("/monitor/errors", dependencies=[Depends(require_admin)])
def get_monitor_errors():
    return {"errors": get_upload_errors()}


# ── 本机环境信息 ──────────────────────────────────────────────
@router.get("/machine-info", dependencies=[Depends(require_admin)])
def get_machine_info():
    """返回本机采集到的环境信息（主机名、域账号、内网IP、公网IP、OS等）"""
    return collect_machine_info()


@router.post("/machine-info/refresh", dependencies=[Depends(require_admin)])
def refresh_machine_info_api():
    """强制重新采集机器信息（公网IP可能变化时使用）"""
    return refresh_machine_info()
