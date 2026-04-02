from __future__ import annotations

import io
import json
import zipfile

from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas.session import ExportRequest
from app.services.export_service import build_export_html_zip, build_export_zip
from app.services.import_service import import_from_zip
from app.services.share_service import create_chat_share


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
async def export_chat_api(request: Request) -> StreamingResponse:
    content_type = (request.headers.get("content-type") or "").lower()
    ids: list[str] = []
    selected_media_paths: list[str] = []
    uploaded_media: list[dict[str, Any]] = []

    try:
        import json as _json

        if "multipart/form-data" in content_type:
            form = await request.form()
            ids = [x for x in _json.loads(str(form.get("ids") or "[]")) if x]
            selected_media_paths = [
                str(x) for x in _json.loads(str(form.get("selectedMediaPaths") or "[]")) if str(x)
            ]

            for file in form.getlist("uploads"):
                if not hasattr(file, "filename"):
                    continue
                content = await file.read()
                if not content:
                    continue
                uploaded_media.append(
                    {
                        "fileName": str(file.filename or "upload.bin"),
                        "mimeType": str(getattr(file, "content_type", "") or ""),
                        "size": len(content),
                        "content": content,
                    }
                )
        else:
            payload = await request.json()
            ids = [x for x in payload.get("ids", []) if x]
            selected_media_paths = [str(x) for x in payload.get("selectedMediaPaths", []) if str(x)]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"参数解析失败: {e}") from e

    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    blob = build_export_html_zip(
        ids,
        selected_media_paths=selected_media_paths,
        uploaded_media=uploaded_media,
    )
    file_name = f"workbuddy-chat-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )



@router.post("/share-chat")
async def share_chat_api(request: Request) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").lower()
    ids: list[str] = []
    selected_media_paths: list[str] = []
    uploaded_media: list[dict[str, Any]] = []

    try:
        import json as _json

        if "multipart/form-data" in content_type:
            form = await request.form()
            ids = [x for x in _json.loads(str(form.get("ids") or "[]")) if x]
            selected_media_paths = [
                str(x) for x in _json.loads(str(form.get("selectedMediaPaths") or "[]")) if str(x)
            ]


            for file in form.getlist("uploads"):
                if not hasattr(file, "filename"):
                    continue
                content = await file.read()
                if not content:
                    continue
                uploaded_media.append(
                    {
                        "fileName": str(file.filename or "upload.bin"),
                        "mimeType": str(getattr(file, "content_type", "") or ""),
                        "size": len(content),
                        "content": content,
                    }
                )
        else:
            payload = await request.json()
            ids = [x for x in payload.get("ids", []) if x]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"参数解析失败: {e}") from e

    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    try:
        return create_chat_share(
            ids,
            str(request.base_url),
            selected_media_paths=selected_media_paths,
            uploaded_media=uploaded_media,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分享失败: {e}") from e



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
