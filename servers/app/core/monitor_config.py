from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

# 配置文件存放在 servers/ 同级的 .monitor_config.json
_CONFIG_PATH = Path(__file__).resolve().parents[2] / ".monitor_config.json"
_lock = threading.Lock()

_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "protocol": "https",         # http | https
    "url": "",                   # 目标上传地址
    "union_id_url": "",          # 获取 union_id 地址（GET 请求，传 platform 参数）
    "delete_url": "",            # 删除数据地址（POST 请求，传 platform 和 union_id 参数）
    "union_id": "",              # 已获取的 union_id（缓存）
    "headers": {},               # 已废弃，由 custom_params 替代（保留用于旧配置迁移）
    "extra_fields": {},          # 已废弃，由 custom_params 替代（保留用于旧配置迁移）
    # 自定义参数列表，每项：{key, value, desc, type: "header"|"body"}
    "custom_params": [],
    "platform_value": "WorkBuddy",   # platform 固定参数的值（可在页面修改）
    "include_basic": True,       # 上传基础对话（user+assistant，仅文本）
    "include_full": False,       # 上传完整对话（含 tool 事件）
    "include_user": True,        # 包含 user 角色消息
    "include_assistant": False,  # 包含 assistant 角色消息（默认不包含）
    "batch_size": 50,            # 每批最多消息数
    "retry_times": 3,            # 失败重试次数
    # ── 响应成功判断 ──────────────────────────────────────────
    # 旧版单字段（保留兼容）
    "success_field": "",
    "success_value": "",
    "success_http_codes": "",
    # 新版多规则（优先级高于旧版）
    # 每项：{enabled, field, op, value}
    # op: eq | ne | gt | gte | lt | lte | contains | not_contains
    "success_rules": [],
}


def load_config() -> dict[str, Any]:
    with _lock:
        if not _CONFIG_PATH.exists():
            return dict(_DEFAULT_CONFIG)
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            cfg = dict(_DEFAULT_CONFIG)
            cfg.update({k: v for k, v in raw.items() if k in _DEFAULT_CONFIG})
            return cfg
        except Exception:
            return dict(_DEFAULT_CONFIG)


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    merged = dict(_DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if k in _DEFAULT_CONFIG})
    with _lock:
        _CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
