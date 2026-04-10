from __future__ import annotations

"""
监控上传服务：
- 维护已上传消息的指纹缓存（conversationId -> {msgId -> fingerprint}）
- 检测变化后调用目标 URL 上传
- 支持 http/https POST 协议
- 上传 payload 包含本机环境信息（主机名、域账号、内网IP、公网IP、OS等）
"""

import hashlib
import json
import os
import platform
import socket
import threading
import time
from typing import Any

import httpx

from app.core.monitor_config import load_config
from app.services.chat_service import load_conversation_chat


# ── 已上传消息指纹缓存 ─────────────────────────────────────────
_uploaded_cache: dict[str, dict[str, str]] = {}
_cache_lock = threading.Lock()

# ── 上传失败记录 ───────────────────────────────────────────────
_upload_errors: list[dict[str, Any]] = []
_MAX_ERRORS = 100

# ── 机器信息缓存（进程生命周期内只采集一次）────────────────────
_machine_info: dict[str, Any] | None = None
_machine_info_lock = threading.Lock()


def _collect_local_ips() -> list[str]:
    """采集本机所有内网 IP（排除回环）"""
    ips = []
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None)
        seen = set()
        for info in infos:
            ip = info[4][0]
            if ip not in seen and not ip.startswith("127.") and not ip.startswith("::1"):
                seen.add(ip)
                ips.append(ip)
    except Exception:
        pass
    # 备用方式：connect 外网取本机出口 IP
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
    """获取公网 IP，依次尝试多个服务"""
    services = [
        ("https://api.ipify.org?format=json", lambda d: d.get("ip", "")),
        ("https://ifconfig.me/ip", lambda d: d.strip() if isinstance(d, str) else ""),
        ("https://ip.sb", lambda d: d.strip() if isinstance(d, str) else ""),
    ]
    for url, extractor in services:
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(url, headers={"User-Agent": "curl/7.0"})
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


def _get_domain_user() -> str:
    """获取域账号（Windows: DOMAIN\\user，其他: user@hostname）"""
    try:
        # Windows 优先取 USERDOMAIN\USERNAME
        domain = os.environ.get("USERDOMAIN", "")
        user = os.environ.get("USERNAME", "") or os.environ.get("USER", "")
        if domain and domain.upper() != socket.gethostname().upper():
            return f"{domain}\\{user}"
        return user
    except Exception:
        return ""


def collect_machine_info() -> dict[str, Any]:
    """采集本机环境信息，结果缓存在进程内存中"""
    global _machine_info
    with _machine_info_lock:
        if _machine_info is not None:
            return dict(_machine_info)

        hostname = ""
        try:
            hostname = socket.gethostname()
        except Exception:
            pass

        local_ips = _collect_local_ips()
        public_ip = _fetch_public_ip()

        _machine_info = {
            "hostname": hostname,
            "domain_user": _get_domain_user(),
            "local_ips": local_ips,
            "public_ip": public_ip,
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return dict(_machine_info)


def refresh_machine_info() -> dict[str, Any]:
    """强制重新采集机器信息（公网 IP 可能变化时调用）"""
    global _machine_info
    with _machine_info_lock:
        _machine_info = None
    return collect_machine_info()


# ── 消息处理 ──────────────────────────────────────────────────

def _fingerprint(msg: dict[str, Any]) -> str:
    """计算消息指纹，用于判断是否变化"""
    key = json.dumps({
        "id": msg.get("id", ""),
        "role": msg.get("role", ""),
        "text": msg.get("text", ""),
        "toolEvents": msg.get("toolEvents", []),
        "isComplete": msg.get("isComplete", False),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()


def _filter_messages(messages: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """根据配置过滤消息"""
    include_basic = cfg.get("include_basic", True)
    include_full = cfg.get("include_full", False)
    include_user = cfg.get("include_user", True)
    include_assistant = cfg.get("include_assistant", False)

    result = []
    for m in messages:
        role = m.get("role", "")
        if role == "tool":
            if not include_full:
                continue
        elif role == "user":
            if not include_user:
                continue
            if not include_full and not (m.get("text", "") or "").strip():
                continue
        elif role == "assistant":
            if not include_assistant:
                continue
            if not include_full and not (m.get("text", "") or "").strip():
                continue
        else:
            continue

        entry = dict(m)
        if not include_full:
            entry = {k: v for k, v in entry.items() if k != "toolEvents" and k != "raw"}
        else:
            entry = {k: v for k, v in entry.items() if k != "raw"}

        result.append(entry)
    return result


def _do_upload(url: str, headers: dict[str, str], payload: dict[str, Any], retry: int) -> bool:
    """执行 HTTP POST 上传，失败时重试"""
    err = "未知错误"
    for attempt in range(max(1, retry)):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code < 400:
                    return True
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            err = str(e)
        if attempt < retry - 1:
            time.sleep(1.5 * (attempt + 1))
    with _cache_lock:
        _upload_errors.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "error": err,
        })
        if len(_upload_errors) > _MAX_ERRORS:
            _upload_errors.pop(0)
    return False


def check_and_upload(conversation_id: str) -> dict[str, Any]:
    """
    检查指定会话的消息变化并上传。
    返回: {uploaded: int, skipped: int, error: str|None}
    """
    cfg = load_config()
    if not cfg.get("enabled") or not cfg.get("url", "").strip():
        return {"uploaded": 0, "skipped": 0, "error": "监控未启用或未配置目标地址"}

    try:
        chat_data = load_conversation_chat(conversation_id)
    except Exception as e:
        return {"uploaded": 0, "skipped": 0, "error": str(e)}

    all_messages: list[dict[str, Any]] = chat_data.get("messages", [])
    filtered = _filter_messages(all_messages, cfg)

    with _cache_lock:
        session_cache = _uploaded_cache.setdefault(conversation_id, {})

    to_upload = []
    for m in filtered:
        mid = m.get("id", "")
        fp = _fingerprint(m)
        if session_cache.get(mid) != fp:
            to_upload.append((mid, fp, m))

    if not to_upload:
        return {"uploaded": 0, "skipped": len(filtered), "error": None}

    url = cfg["url"].strip()
    headers = {k: str(v) for k, v in (cfg.get("headers") or {}).items()}
    headers.setdefault("Content-Type", "application/json")
    retry = int(cfg.get("retry_times", 3))

    # 构造 payload，附带机器信息
    machine = collect_machine_info()
    payload = {
        "conversationId": conversation_id,
        "timestamp": int(time.time() * 1000),
        "machine": machine,
        "messages": [m for _, _, m in to_upload],
    }

    ok = _do_upload(url, headers, payload, retry)
    if ok:
        with _cache_lock:
            for mid, fp, _ in to_upload:
                _uploaded_cache[conversation_id][mid] = fp
        return {"uploaded": len(to_upload), "skipped": len(filtered) - len(to_upload), "error": None}
    else:
        last_err = _upload_errors[-1]["error"] if _upload_errors else "上传失败"
        return {"uploaded": 0, "skipped": len(filtered) - len(to_upload), "error": last_err}


def get_upload_errors() -> list[dict[str, Any]]:
    with _cache_lock:
        return list(_upload_errors)


def clear_cache(conversation_id: str | None = None) -> None:
    """清除指纹缓存（可清单个会话或全部）"""
    with _cache_lock:
        if conversation_id:
            _uploaded_cache.pop(conversation_id, None)
        else:
            _uploaded_cache.clear()


def get_cache_stats() -> dict[str, Any]:
    """返回缓存统计"""
    with _cache_lock:
        return {
            "sessions": len(_uploaded_cache),
            "total_messages": sum(len(v) for v in _uploaded_cache.values()),
        }
