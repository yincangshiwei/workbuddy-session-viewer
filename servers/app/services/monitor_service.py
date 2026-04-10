from __future__ import annotations

"""
监控上传服务（SQLite 持久化版本）

流程：
1. 初始化（initialize_sync）：
   - 从所有活跃会话读取消息，写入 SQLite，状态全部置为"未同步"
   - 换服务地址/重置时调用此接口

2. 监控轮询（check_and_upload_all / check_and_upload）：
   - 读取当前会话消息，与 DB 中指纹对比
   - 新消息/内容变化 → upsert 到 DB（状态=未同步）
   - 取出 DB 中所有未同步记录 → 上传 → 成功后标记为已同步
"""

import hashlib
import json
import os
import platform
import re
import socket
import threading
import time
from typing import Any

import httpx

from app.core.monitor_config import load_config
from app.core.monitor_db import (
    get_stats,
    get_unsynced,
    mark_synced,
    reset_all,
    upsert_messages,
)
from app.services.chat_service import load_conversation_chat
from app.services.session_service import load_sessions


# ── 上传失败记录 ───────────────────────────────────────────────
_upload_errors: list[dict[str, Any]] = []
_errors_lock = threading.Lock()
_MAX_ERRORS = 100

# ── 机器信息缓存 ───────────────────────────────────────────────
_machine_info: dict[str, Any] | None = None
_machine_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════
# 机器信息采集
# ═══════════════════════════════════════════════════════════════

def _collect_local_ips() -> list[str]:
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127.") and ip != "::1":
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips


def _fetch_public_ip() -> str:
    services = [
        ("https://api.ipify.org?format=json", lambda d: d.get("ip", "") if isinstance(d, dict) else ""),
        ("https://ifconfig.me/ip", lambda d: d.strip() if isinstance(d, str) else ""),
        ("https://ip.sb", lambda d: d.strip() if isinstance(d, str) else ""),
    ]
    for url, extractor in services:
        try:
            with httpx.Client(timeout=5) as c:
                resp = c.get(url, headers={"User-Agent": "curl/7.0"})
                if resp.status_code == 200:
                    try:
                        result = extractor(resp.json())
                    except Exception:
                        result = extractor(resp.text)
                    if result:
                        return result
        except Exception:
            continue
    return ""


def collect_machine_info() -> dict[str, Any]:
    global _machine_info
    with _machine_lock:
        if _machine_info is not None:
            return dict(_machine_info)
        hostname = ""
        try:
            hostname = socket.gethostname()
        except Exception:
            pass
        domain = os.environ.get("USERDOMAIN", "")
        user = os.environ.get("USERNAME", "") or os.environ.get("USER", "")
        domain_user = f"{domain}\\{user}" if domain and domain.upper() != hostname.upper() else user

        _machine_info = {
            "hostname": hostname,
            "domain_user": domain_user,
            "local_ips": _collect_local_ips(),
            "public_ip": _fetch_public_ip(),
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return dict(_machine_info)


def refresh_machine_info() -> dict[str, Any]:
    global _machine_info
    with _machine_lock:
        _machine_info = None
    return collect_machine_info()


# ═══════════════════════════════════════════════════════════════
# 消息处理工具
# ═══════════════════════════════════════════════════════════════

def _extract_user_query(text: str) -> str:
    """提取 <user_query> 标签中最后一段内容，与前端 extractUserQuery 逻辑完全一致"""
    matches = re.findall(r"<user_query>\s*([\s\S]*?)\s*</user_query>", text, re.IGNORECASE)
    if matches:
        return matches[-1].strip()
    return ""


def _resolve_display_text(role: str, raw_text: str) -> str:
    """
    与页面展示完全一致：
    - user 消息：有 <user_query> 标签则取最后一段，否则用原始 text
    - 其他角色：直接用原始 text
    页面逻辑：displayText = userQueryText || m.text
    """
    if role == "user":
        extracted = _extract_user_query(raw_text)
        return extracted if extracted else raw_text
    return raw_text


def _fingerprint(msg: dict[str, Any]) -> str:
    key = json.dumps({
        "id": msg.get("id", ""),
        "role": msg.get("role", ""),
        "text": msg.get("text", ""),
        "toolEvents": msg.get("toolEvents", []),
        "isComplete": msg.get("isComplete", False),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()


def _filter_messages(messages: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """
    根据配置过滤消息，text 字段处理为与页面展示完全一致的内容：
    - user 消息：提取 <user_query> 最后一段（有则用，无则用原始 text）
    - assistant 消息：原始 text
    - 基础对话模式：去掉 toolEvents/raw
    - 完整对话模式：去掉 raw，保留 toolEvents
    """
    include_full = cfg.get("include_full", False)
    include_user = cfg.get("include_user", True)
    include_assistant = cfg.get("include_assistant", False)

    result = []
    for m in messages:
        role = m.get("role", "")
        raw_text = m.get("text", "") or ""

        if role == "tool":
            if not include_full:
                continue
        elif role == "user":
            if not include_user:
                continue
            if not include_full and not raw_text.strip():
                continue
        elif role == "assistant":
            if not include_assistant:
                continue
            if not include_full and not raw_text.strip():
                continue
        else:
            continue

        entry = dict(m)

        # text 字段替换为与页面展示一致的内容
        entry["text"] = _resolve_display_text(role, raw_text)

        if not include_full:
            entry = {k: v for k, v in entry.items() if k not in ("toolEvents", "raw")}
        else:
            entry = {k: v for k, v in entry.items() if k != "raw"}

        result.append(entry)
    return result


# ═══════════════════════════════════════════════════════════════
# 初始化：清空 DB，重新扫描所有会话写入，状态=未同步
# ═══════════════════════════════════════════════════════════════

def initialize_sync() -> dict[str, Any]:
    """
    初始化同步数据：
    1. 读取所有活跃会话的消息（按当前配置过滤）
    2. 清空 DB，写入全部消息，状态=未同步
    返回 {total: int, conversations: int, error: str|None}
    """
    cfg = load_config()
    sessions = load_sessions()
    active = [s for s in sessions if not s.get("deletedAt")]

    all_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for s in active:
        cid = s.get("conversationId", "")
        if not cid:
            continue
        try:
            chat = load_conversation_chat(cid)
            filtered = _filter_messages(chat.get("messages", []), cfg)
            for m in filtered:
                all_rows.append({
                    "conversation_id": cid,
                    "message_id": m.get("id", ""),
                    "role": m.get("role", ""),
                    "fingerprint": _fingerprint(m),
                    "created_at": m.get("createdAt", ""),
                })
        except Exception as e:
            errors.append(f"{cid}: {e}")

    total = reset_all(all_rows)
    return {
        "total": total,
        "conversations": len(active),
        "errors": errors,
        "error": errors[0] if errors else None,
    }


# ═══════════════════════════════════════════════════════════════
# 增量检测：扫描单个会话，更新 DB 中的变化
# ═══════════════════════════════════════════════════════════════

def _scan_conversation(cid: str, cfg: dict[str, Any]) -> dict[str, int]:
    """
    扫描单个会话，将新消息/变化消息 upsert 到 DB（状态=未同步）。
    返回 {new, changed, unchanged}
    """
    try:
        chat = load_conversation_chat(cid)
        filtered = _filter_messages(chat.get("messages", []), cfg)
    except Exception:
        return {"new": 0, "changed": 0, "unchanged": 0}

    rows = [{
        "conversation_id": cid,
        "message_id": m.get("id", ""),
        "role": m.get("role", ""),
        "fingerprint": _fingerprint(m),
        "created_at": m.get("createdAt", ""),
    } for m in filtered]

    diff = upsert_messages(rows)
    return {
        "new": len(diff["new"]),
        "changed": len(diff["changed"]),
        "unchanged": len(diff["unchanged"]),
    }


# ═══════════════════════════════════════════════════════════════
# 上传：取出 DB 未同步记录 → 拼装消息内容 → POST → 标记已同步
# ═══════════════════════════════════════════════════════════════

def _record_error(url: str, err: str) -> None:
    with _errors_lock:
        _upload_errors.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "error": err,
        })
        if len(_upload_errors) > _MAX_ERRORS:
            _upload_errors.pop(0)


def _do_upload(url: str, headers: dict[str, str], payload: dict[str, Any], retry: int) -> tuple[bool, str]:
    err = "未知错误"
    for attempt in range(max(1, retry)):
        try:
            with httpx.Client(timeout=15) as c:
                resp = c.post(url, json=payload, headers=headers)
                if resp.status_code < 400:
                    return True, ""
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            err = str(e)
        if attempt < retry - 1:
            time.sleep(1.5 * (attempt + 1))
    _record_error(url, err)
    return False, err


def _build_message_content(unsynced_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    按 conversation_id 分组，从磁盘重新读取消息内容（指纹只做比对，内容要实时读）。
    返回 {cid: [message, ...]}
    """
    from app.services.common import resolve_transcript_index, safe_json, ts_to_text
    import json as _json

    # 按会话分组
    by_conv: dict[str, list[str]] = {}
    for row in unsynced_rows:
        cid = row["conversation_id"]
        mid = row["message_id"]
        by_conv.setdefault(cid, []).append(mid)

    result: dict[str, list[dict[str, Any]]] = {}
    for cid, mids in by_conv.items():
        mid_set = set(mids)
        try:
            chat = load_conversation_chat(cid)
            cfg = load_config()
            filtered = _filter_messages(chat.get("messages", []), cfg)
            result[cid] = [m for m in filtered if m.get("id", "") in mid_set]
        except Exception:
            result[cid] = []
    return result


def upload_unsynced(conversation_id: str | None = None) -> dict[str, Any]:
    """
    上传所有未同步记录（或指定会话）。
    返回 {uploaded, failed, error}
    """
    cfg = load_config()
    if not cfg.get("enabled") or not cfg.get("url", "").strip():
        return {"uploaded": 0, "failed": 0, "error": "监控未启用或未配置目标地址"}

    unsynced = get_unsynced(conversation_id=conversation_id, limit=500)
    if not unsynced:
        return {"uploaded": 0, "failed": 0, "error": None}

    url = cfg["url"].strip()
    headers = {k: str(v) for k, v in (cfg.get("headers") or {}).items()}
    headers.setdefault("Content-Type", "application/json")
    retry = int(cfg.get("retry_times", 3))
    machine = collect_machine_info()

    # 读取实际消息内容
    content_map = _build_message_content(unsynced)

    # 按会话分批上传
    uploaded_pks: list[str] = []
    failed_pks: list[str] = []

    # 构建 pk -> row 映射
    pk_to_row = {r["id"]: r for r in unsynced}

    # 按会话聚合 pk
    by_conv: dict[str, list[str]] = {}
    for row in unsynced:
        by_conv.setdefault(row["conversation_id"], []).append(row["id"])

    for cid, pks in by_conv.items():
        messages = content_map.get(cid, [])
        if not messages:
            # 消息读取失败，跳过（保持未同步）
            failed_pks.extend(pks)
            continue

        payload = {
            "conversationId": cid,
            "timestamp": int(time.time() * 1000),
            "machine": machine,
            "messages": messages,
        }
        ok, err_msg = _do_upload(url, headers, payload, retry)
        if ok:
            uploaded_pks.extend(pks)
        else:
            failed_pks.extend(pks)

    if uploaded_pks:
        mark_synced(uploaded_pks)

    return {
        "uploaded": len(uploaded_pks),
        "failed": len(failed_pks),
        "error": None if not failed_pks else "部分会话上传失败，请查看错误日志",
    }


# ═══════════════════════════════════════════════════════════════
# 完整轮询：扫描变化 + 上传未同步
# ═══════════════════════════════════════════════════════════════

def poll_and_upload() -> dict[str, Any]:
    """
    一次完整的监控轮询：
    1. 扫描所有活跃会话，检测新消息/变化 → 写入 DB（未同步）
    2. 上传所有未同步记录
    """
    cfg = load_config()
    sessions = load_sessions()
    active = [s for s in sessions if not s.get("deletedAt")]

    scan_new = 0
    scan_changed = 0
    for s in active:
        cid = s.get("conversationId", "")
        if not cid:
            continue
        diff = _scan_conversation(cid, cfg)
        scan_new += diff["new"]
        scan_changed += diff["changed"]

    upload_result = upload_unsynced()

    return {
        "scanned_sessions": len(active),
        "scan_new": scan_new,
        "scan_changed": scan_changed,
        "uploaded": upload_result["uploaded"],
        "failed": upload_result["failed"],
        "error": upload_result.get("error"),
    }


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def get_sync_stats() -> dict[str, Any]:
    return get_stats()


def get_upload_errors() -> list[dict[str, Any]]:
    with _errors_lock:
        return list(_upload_errors)
