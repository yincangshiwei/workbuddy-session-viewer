from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.session_service import load_sessions

router = APIRouter()


@router.get("/sessions")
def get_sessions() -> dict[str, Any]:
    sessions = load_sessions()
    return {"total": len(sessions), "sessions": sessions}
