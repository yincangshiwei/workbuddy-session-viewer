from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas.session import ModelsConfigSaveRequest
from app.services.model_config_service import load_models_config, save_models_config

router = APIRouter()


@router.get("/config/models")
def get_models_config() -> dict[str, Any]:
    try:
        return load_models_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/config/models")
def save_models_config_api(payload: ModelsConfigSaveRequest) -> dict[str, Any]:
    try:
        data = save_models_config(payload.models, payload.config)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"success": True, **data}
