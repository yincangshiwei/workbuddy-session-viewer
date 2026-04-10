from __future__ import annotations

# 全局管理模式标志，由启动参数 --admin 设置
_admin_mode: bool = False


def set_admin_mode(enabled: bool) -> None:
    global _admin_mode
    _admin_mode = enabled


def is_admin_mode() -> bool:
    return _admin_mode
