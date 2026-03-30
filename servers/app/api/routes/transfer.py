from __future__ import annotations

import io
import zipfile
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas.session import ExportRequest
from app.services.export_service import build_export_html_zip, build_export_zip
from app.services.import_service import import_from_zip

router = APIRouter()


@router.post("/export")
def export_api(payload: ExportRequest) -> StreamingResponse:
    ids = [x for x in payload.ids if x]
    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    blob = build_export_zip(ids)
    file_name = f"workbuddy-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/export-chat")
def export_chat_api(payload: ExportRequest) -> StreamingResponse:
    ids = [x for x in payload.ids if x]
    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    blob = build_export_html_zip(ids)
    file_name = f"workbuddy-chat-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/import")
async def import_api(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file required")

    try:
        content = await file.read()
        result = import_from_zip(content)
        return result
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="invalid zip file") from e
