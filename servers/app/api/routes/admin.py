from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Any

from app.core.admin_state import is_admin_mode
from app.core.monitor_config import load_config, save_config
from app.core.monitor_db import get_messages_page
from app.services.monitor_service import (
    clear_live_logs,
    collect_machine_info,
    fetch_union_id,
    delete_remote_data,
    get_live_logs,
    get_sync_stats,
    get_upload_errors,
    initialize_sync,
    poll_and_upload,
    preview_upload_payload,
    refresh_machine_info,
    request_cancel,
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


class CustomParamItem(BaseModel):
    key: str = ""
    value: str = ""
    desc: str = ""
    type: str = "header"   # "header" | "body"


class SuccessRuleItem(BaseModel):
    enabled: bool = True
    field: str = ""
    op: str = "eq"   # eq | ne | gt | gte | lt | lte | contains | not_contains
    value: str = ""


class MonitorConfigIn(BaseModel):
    enabled: bool = False
    protocol: str = "https"
    url: str = ""
    union_id_url: str = ""
    delete_url: str = ""
    union_id: str = ""
    platform_value: str = "WorkBuddy"
    custom_params: list[CustomParamItem] = []
    include_basic: bool = True
    include_full: bool = False
    include_user: bool = True
    include_assistant: bool = False
    batch_size: int = 50
    retry_times: int = 3
    # 响应成功判断（旧版保留兼容）
    success_field: str = ""
    success_value: str = ""
    success_http_codes: str = ""
    # 新版多规则
    success_rules: list[SuccessRuleItem] = []


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


# ── 停止正在执行的轮询/上传 ───────────────────────────────────
@router.post("/monitor/stop", dependencies=[Depends(require_admin)])
def stop_poll():
    """请求取消当前正在执行的轮询或上传操作"""
    request_cancel()
    return {"success": True}


# ── 上传错误日志 ──────────────────────────────────────────────
@router.get("/monitor/errors", dependencies=[Depends(require_admin)])
def get_monitor_errors():
    return {"errors": get_upload_errors()}


# ── 实时日志（前端轮询拉取）──────────────────────────────────
@router.get("/monitor/live-logs", dependencies=[Depends(require_admin)])
def get_monitor_live_logs(since: int = Query(0, description="只返回 id > since 的日志")):
    """拉取后端实时推送的监控日志（增量查询）"""
    return get_live_logs(since_id=since)


@router.post("/monitor/live-logs/clear", dependencies=[Depends(require_admin)])
def clear_monitor_live_logs():
    """清空实时日志缓冲区"""
    clear_live_logs()
    return {"success": True}


# ── 本机环境信息 ──────────────────────────────────────────────
@router.get("/machine-info", dependencies=[Depends(require_admin)])
def get_machine_info():
    return collect_machine_info()


@router.post("/machine-info/refresh", dependencies=[Depends(require_admin)])
def refresh_machine_info_api():
    return refresh_machine_info()


# ── 上传 Payload 预览 ─────────────────────────────────────────
@router.get("/monitor/payload-preview", dependencies=[Depends(require_admin)])
def get_payload_preview(
    conversation_id: str = Query(..., description="用于预览的会话ID"),
    max_messages: int = Query(3, ge=1, le=20, description="最多展示几条消息"),
):
    """
    根据当前配置，构造真实上传 payload 的示例结构（不实际发送）。
    用于在配置页面展示会上传什么内容给服务端。
    """
    return preview_upload_payload(conversation_id, max_messages=max_messages)


# ── 获取 union_id ─────────────────────────────────────────────
@router.get("/monitor/union-id", dependencies=[Depends(require_admin)])
def get_union_id_api(
    platform: str = Query(..., description="平台标识"),
    url: str = Query("", description="获取 union_id 的地址，为空时从已保存配置读取"),
):
    """通过指定地址（或已保存配置的 union_id_url）发送 GET 请求获取 union_id"""
    return fetch_union_id(platform=platform, url=url or None)



# ── 删除远端数据 ──────────────────────────────────────────────
class DeleteDataIn(BaseModel):
    platform: str
    union_id: str
    url: str = ""   # 为空时从已保存配置读取


@router.post("/monitor/delete-data", dependencies=[Depends(require_admin)])
def delete_data_api(body: DeleteDataIn):
    """通过指定地址（或已保存配置的 delete_url）发送 POST 请求删除远端数据"""
    return delete_remote_data(platform=body.platform, union_id=body.union_id, url=body.url or None)

