from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.settings import SHARE_BASE
from app.core.admin_state import set_admin_mode
from app.core.monitor_db import init_db

# ── 管理员模式：通过环境变量 WORKBUDDY_ADMIN=1 激活 ─────────────
if os.getenv("WORKBUDDY_ADMIN", "").strip() in ("1", "true", "yes"):
    set_admin_mode(True)

# ── 启动时确保 SQLite DB 和表结构已创建（DB 文件不存在时自动创建）──
init_db()

# ── FastAPI 应用 ─────────────────────────────────────────────
app = FastAPI(title="WorkBuddy Session Viewer API")

allow_origins = os.getenv(
    "ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
)

def _build_origins(raw: str) -> list[str]:
    """
    解析 ALLOW_ORIGINS，支持通配符 *。
    开发模式下默认允许所有来源（前端 host=0.0.0.0 后局域网 IP 会动态变化）。
    生产模式（静态托管）同源请求不经过 CORS，无需额外配置。
    """
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    return origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_origins(allow_origins),
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

shared_dir = SHARE_BASE.resolve()
shared_dir.mkdir(parents=True, exist_ok=True)
app.mount("/shared", StaticFiles(directory=str(shared_dir), html=True), name="shared")

static_dir = (Path(__file__).resolve().parents[1] / "static").resolve()
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
