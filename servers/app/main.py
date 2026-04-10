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

allow_origins = os.getenv("ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in allow_origins.split(",") if x.strip()],
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
