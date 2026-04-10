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
    "headers": {},               # 自定义请求头（如鉴权 token）
    "include_basic": True,       # 上传基础对话（user+assistant，仅文本）
    "include_full": False,       # 上传完整对话（含 tool 事件）
    "include_user": True,        # 包含 user 角色消息
    "include_assistant": False,  # 包含 assistant 角色消息（默认不包含）
    "batch_size": 50,            # 每批最多消息数
    "retry_times": 3,            # 失败重试次数
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
