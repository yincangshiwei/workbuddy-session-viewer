from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse


from app.schemas.session import PathActionRequest

router = APIRouter()


def _existing_path(raw_path: str) -> Path:
    path = Path(str(raw_path or "")).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return path


def _open_in_system(path: Path) -> None:
    target = str(path)
    if os.name == "nt":
        startfile = getattr(os, "startfile", None)
        if not startfile:
            raise RuntimeError("当前系统不支持该操作")
        startfile(target)
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
        return
    subprocess.Popen(["xdg-open", target])


def _locate_in_system(path: Path) -> None:

    target = path.resolve()
    if os.name == "nt":
        if path.is_file():
            subprocess.Popen(["explorer.exe", "/select,", str(target)])
        else:
            subprocess.Popen(["explorer.exe", str(target)])
        return
    if sys.platform == "darwin":
        if path.is_file():
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["open", str(target)])
        return
    _open_in_system(target.parent if path.is_file() else target)



@router.get("/local/open-file")
def open_file_api(path: str = Query(default="")) -> FileResponse:
    target = _existing_path(path)
    if not target.is_file():
        raise HTTPException(status_code=400, detail="目标不是文件")
    response = FileResponse(path=str(target))
    response.headers["Content-Disposition"] = "inline"
    return response



@router.post("/local/locate-file")
def locate_file_api(payload: PathActionRequest) -> dict[str, bool]:
    path = _existing_path(payload.path)
    target_dir = path.parent if path.is_file() else path
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="所在目录不存在")
    try:
        _locate_in_system(path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"打开目录失败: {exc}") from exc
    return {"success": True}

