from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.chat_service import load_conversation_chat

router = APIRouter()


@router.get("/session/{cid}/chat")
def get_session_chat(cid: str) -> dict[str, Any]:
    if not cid:
        raise HTTPException(status_code=400, detail="cid required")
    return load_conversation_chat(cid)
