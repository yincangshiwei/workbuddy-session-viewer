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

# ── 轮询取消标志 ───────────────────────────────────────────────
_cancel_event = threading.Event()


def request_cancel() -> None:
    """请求取消当前正在执行的轮询/上传"""
    _cancel_event.set()


def _is_cancelled() -> bool:
    return _cancel_event.is_set()


# ── 实时日志缓冲区（前端独立拉取）────────────────────────────
_live_logs: list[dict[str, Any]] = []   # [{id, msg, type, ts}]
_live_logs_lock = threading.Lock()
_live_log_counter = 0


def _push_log(msg: str, log_type: str = "info") -> None:
    """向实时日志缓冲区追加一条日志"""
    global _live_log_counter
    with _live_logs_lock:
        _live_log_counter += 1
        _live_logs.append({
            "id": _live_log_counter,
            "msg": msg,
            "type": log_type,
            "ts": time.strftime("%H:%M:%S"),
        })
        # 最多保留 500 条
        if len(_live_logs) > 500:
            _live_logs[:] = _live_logs[-500:]


def get_live_logs(since_id: int = 0) -> dict[str, Any]:
    """获取 since_id 之后的所有日志条目"""
    with _live_logs_lock:
        if since_id <= 0:
            entries = list(_live_logs)
        else:
            entries = [e for e in _live_logs if e["id"] > since_id]
        return {"logs": entries}


def clear_live_logs() -> None:
    """清空实时日志缓冲区"""
    global _live_log_counter
    with _live_logs_lock:
        _live_logs.clear()
        _live_log_counter = 0


# ── 机器信息缓存 ───────────────────────────────────────────────
_machine_info: dict[str, Any] | None = None
_machine_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════
# 机器信息采集
# ═══════════════════════════════════════════════════════════════

# 虚拟/VPN 网段前缀，优先级最低（排除在 local_ip 之外）
_SKIP_PREFIXES = (
    "26.",        # ZeroTier / Hamachi
    "25.",        # Hamachi
    "100.64.",    # CGNAT / Tailscale
    "169.254.",   # APIPA 链路本地
    "172.16.",    "172.17.",    "172.18.",    "172.19.",
    "172.20.",    "172.21.",    "172.22.",    "172.23.",
    "172.24.",    "172.25.",    "172.26.",    "172.27.",
    "172.28.",    "172.29.",    "172.30.",    "172.31.",  # Docker 默认桥接段
)

# 真实私有网段优先级（越靠前越优先）
_PREFER_PREFIXES = (
    "10.",        # 企业内网 / WiFi 常见
    "192.168.",   # 家庭/办公 WiFi 最常见
)


def _score_ip(ip: str) -> int:
    """
    给 IP 打优先级分（分越低越优先）。
    IPv6 / 虚拟网段 → 高分（靠后）；真实私有 IPv4 → 低分（靠前）。
    """
    if ":" in ip:
        return 100  # IPv6 最低优先
    for prefix in _SKIP_PREFIXES:
        if ip.startswith(prefix):
            return 90  # 虚拟/VPN 网段
    for i, prefix in enumerate(_PREFER_PREFIXES):
        if ip.startswith(prefix):
            return i   # 0 = 最高优先（10.x.x.x），1 = 次之（192.168.x.x）
    return 50  # 其他公网 IP


def _get_primary_local_ip(all_ips: list[str]) -> str:
    """
    从已收集的所有 IP 中，按优先级选出最可能是真实物理网卡的 IPv4 地址。
    优先顺序：10.x.x.x > 192.168.x.x > 其他私有 > 公网 IPv4 > IPv6 > 虚拟网段
    """
    candidates = [ip for ip in all_ips if ":" not in ip]  # 只看 IPv4
    if not candidates:
        return ""
    candidates.sort(key=_score_ip)
    return candidates[0]


def _collect_local_ips() -> list[str]:
    """收集所有本地 IP（含虚拟网卡），过滤回环和 IPv6 链路本地地址"""
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127.") and ip != "::1":
                ips.append(ip)
    except Exception:
        pass
    # 备用：UDP connect trick
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                ips.append(ip)
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

        # 先收集所有本地 IP，再从中按优先级选出主网卡 IP
        all_ips = _collect_local_ips()
        primary_ip = _get_primary_local_ip(all_ips)

        _machine_info = {
            "hostname": hostname,
            "domain_user": domain_user,
            "local_ip": primary_ip,          # 主网卡 IP（优先选 10.x / 192.168.x，排除虚拟网段）
            "local_ips": all_ips,            # 所有本地 IP（含虚拟网卡，供参考）
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


def _is_success(resp: httpx.Response, cfg: dict[str, Any]) -> tuple[bool, str]:
    """
    判断上传是否成功，优先级：
    1. 若配置了 success_http_codes（如 "200,201"），只认这些状态码
    2. 若配置了 success_field + success_value，解析响应体 JSON 判断
    3. 兜底：HTTP 状态码 < 400 视为成功
    返回 (is_ok, err_reason)
    """
    status = resp.status_code

    # ── 方式一：指定状态码列表 ──
    raw_codes = (cfg.get("success_http_codes") or "").strip()
    if raw_codes:
        allowed = {int(c.strip()) for c in raw_codes.split(",") if c.strip().isdigit()}
        if status not in allowed:
            return False, f"HTTP {status} 不在成功状态码列表 [{raw_codes}] 中"
        # 状态码通过后，如果还配了字段判断则继续检查
        field = (cfg.get("success_field") or "").strip()
        if not field:
            return True, ""
    else:
        # 未配置状态码列表，先做 < 400 兜底检查
        if status >= 400:
            return False, f"HTTP {status}: {resp.text[:200]}"
        field = (cfg.get("success_field") or "").strip()
        if not field:
            return True, ""

    # ── 方式二：解析响应体 JSON 字段 ──
    expected_raw = (cfg.get("success_value") or "").strip()
    try:
        body = resp.json()
    except Exception:
        return False, f"响应体非 JSON，无法按字段 '{field}' 判断"

    if not isinstance(body, dict):
        return False, f"响应体不是 JSON 对象，无法按字段 '{field}' 判断"

    actual = body.get(field)
    if actual is None:
        return False, f"响应体中不存在字段 '{field}'"

    # 将实际值转为字符串做宽松比较（兼容 true/True/1/"true"/"1" 等）
    actual_str = str(actual).lower()
    expected_str = expected_raw.lower()

    # 特殊处理：true/false 布尔兼容
    bool_map = {"true": True, "1": True, "false": False, "0": False}
    actual_norm = bool_map.get(actual_str, actual_str)
    expected_norm = bool_map.get(expected_str, expected_str)

    if actual_norm == expected_norm:
        return True, ""
    return False, f"响应字段 '{field}'={actual!r}，期望值={expected_raw!r}"


def _do_upload(url: str, headers: dict[str, str], payload: dict[str, Any], retry: int, cfg: dict[str, Any]) -> tuple[bool, str]:
    """执行 HTTP POST 上传，失败时重试，根据 cfg 中的成功判断规则决定是否成功"""
    err = "未知错误"
    for attempt in range(max(1, retry)):
        try:
            with httpx.Client(timeout=15) as c:
                resp = c.post(url, json=payload, headers=headers)
            ok, reason = _is_success(resp, cfg)
            if ok:
                return True, ""
            err = reason
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


def _upload_unsynced_with_logs() -> dict[str, Any]:
    """与 upload_unsynced 逻辑相同，但将每步进度实时推送到日志缓冲区。"""
    cfg = load_config()
    if not cfg.get("enabled") or not cfg.get("url", "").strip():
        _push_log("监控未启用或未配置目标地址，跳过上传", "info")
        return {"uploaded": 0, "failed": 0, "error": "监控未启用或未配置目标地址"}

    unsynced = get_unsynced(limit=500)
    if not unsynced:
        _push_log("无待上传记录", "info")
        return {"uploaded": 0, "failed": 0, "error": None}

    # 按会话聚合
    by_conv: dict[str, list[str]] = {}
    for row in unsynced:
        by_conv.setdefault(row["conversation_id"], []).append(row["id"])

    _push_log(f"开始上传：{len(unsynced)} 条未同步记录（{len(by_conv)} 个会话）", "info")

    url = cfg["url"].strip()
    headers = {k: str(v) for k, v in (cfg.get("headers") or {}).items()}
    headers.setdefault("Content-Type", "application/json")
    retry = int(cfg.get("retry_times", 3))
    machine = collect_machine_info()
    content_map = _build_message_content(unsynced)

    uploaded_pks: list[str] = []
    failed_pks: list[str] = []
    conv_idx = 0

    for cid, pks in by_conv.items():
        if _is_cancelled():
            _push_log(f"上传阶段被取消（已处理 {conv_idx}/{len(by_conv)}）", "info")
            break
        conv_idx += 1
        short_id = cid[:12]
        messages = content_map.get(cid, [])
        if not messages:
            failed_pks.extend(pks)
            _push_log(f"上传 [{short_id}]：消息读取失败，跳过（{len(pks)} 条）", "error")
            continue

        payload = {
            "conversationId": cid,
            "timestamp": int(time.time() * 1000),
            "machine": machine,
            "messages": messages,
        }
        ok, err_msg = _do_upload(url, headers, payload, retry, cfg)
        if ok:
            uploaded_pks.extend(pks)
            _push_log(f"上传 [{short_id}]：成功（{len(messages)} 条消息）[{conv_idx}/{len(by_conv)}]", "success")
        else:
            failed_pks.extend(pks)
            _push_log(f"上传 [{short_id}]：失败 - {err_msg}（{len(messages)} 条消息）", "error")

    if uploaded_pks:
        mark_synced(uploaded_pks)

    if uploaded_pks or failed_pks:
        _push_log(
            f"上传完成：成功 {len(uploaded_pks)} 条，失败 {len(failed_pks)} 条",
            "success" if not failed_pks else "error",
        )

    return {
        "uploaded": len(uploaded_pks),
        "failed": len(failed_pks),
        "error": None if not failed_pks else "部分会话上传失败，请查看错误日志",
    }


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
        if _is_cancelled():
            break
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
        ok, err_msg = _do_upload(url, headers, payload, retry, cfg)
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
    支持通过 request_cancel() 中途取消。
    日志实时推送到共享缓冲区，前端通过 GET /monitor/live-logs 拉取。
    """
    _cancel_event.clear()

    cfg = load_config()
    sessions = load_sessions()
    active = [s for s in sessions if not s.get("deletedAt")]

    _push_log(f"开始扫描 {len(active)} 个活跃会话...", "info")

    scan_new = 0
    scan_changed = 0
    scanned_count = 0
    cancelled = False
    for s in active:
        if _is_cancelled():
            cancelled = True
            _push_log(f"扫描阶段被取消（已完成 {scanned_count}/{len(active)}）", "info")
            break
        cid = s.get("conversationId", "")
        if not cid:
            continue
        title = s.get("title", "") or cid[:12]
        diff = _scan_conversation(cid, cfg)
        scanned_count += 1
        n, c = diff["new"], diff["changed"]
        scan_new += n
        scan_changed += c
        if n or c:
            parts = []
            if n:
                parts.append(f"{n} 条新消息")
            if c:
                parts.append(f"{c} 条变化")
            _push_log(f"扫描 [{title}]：{'、'.join(parts)}", "success")

    if not cancelled:
        _push_log(
            f"扫描完成：共 {scanned_count} 个会话，{scan_new} 条新消息、{scan_changed} 条变化",
            "success" if (scan_new or scan_changed) else "info",
        )

    if not cancelled and not _is_cancelled():
        upload_result = _upload_unsynced_with_logs()
    else:
        cancelled = True
        upload_result = {"uploaded": 0, "failed": 0, "error": None}

    return {
        "cancelled": cancelled,
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


# ═══════════════════════════════════════════════════════════════
# Payload 预览：构造真实上传结构，不实际发送
# ═══════════════════════════════════════════════════════════════

def preview_upload_payload(conversation_id: str, max_messages: int = 3) -> dict[str, Any]:
    """
    根据当前配置，构造会上传到目标服务器的 payload 示例（不实际发送）。
    - 按当前配置过滤消息（include_user/include_assistant/include_full 等）
    - 最多返回 max_messages 条消息作为示例
    - 包含真实的 machine 信息
    """
    cfg = load_config()
    try:
        chat = load_conversation_chat(conversation_id)
    except Exception as e:
        return {"error": str(e), "payload": None}

    all_messages = chat.get("messages", [])
    filtered = _filter_messages(all_messages, cfg)

    # 截取前 max_messages 条作为示例
    sample = filtered[:max_messages]
    total_filtered = len(filtered)

    machine = collect_machine_info()

    payload = {
        "conversationId": conversation_id,
        "timestamp": int(time.time() * 1000),
        "machine": machine,
        "messages": sample,
    }

    return {
        "error": None,
        "payload": payload,
        "total_messages": total_filtered,
        "sample_count": len(sample),
        "config_summary": {
            "include_basic": cfg.get("include_basic", True),
            "include_full": cfg.get("include_full", False),
            "include_user": cfg.get("include_user", True),
            "include_assistant": cfg.get("include_assistant", False),
        },
    }
