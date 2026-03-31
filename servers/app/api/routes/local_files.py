from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def _build_workspace_tree_node(path: Path, root: Path) -> tuple[dict[str, Any], int, int]:
    rel_path = "." if path == root else str(path.relative_to(root)).replace("\\", "/")
    node: dict[str, Any] = {
        "name": path.name or str(path),
        "relativePath": rel_path,
        "filePath": str(path),
        "type": "dir",
        "children": [],
    }

    dirs: list[Path] = []
    files: list[Path] = []
    try:
        for child in path.iterdir():
            if child.is_symlink():
                continue
            if child.is_dir():
                dirs.append(child)
            elif child.is_file():
                files.append(child)
    except Exception:
        return node, 0, 0


    dirs.sort(key=lambda p: p.name.lower())
    files.sort(key=lambda p: p.name.lower())

    dir_count = 0
    file_count = 0
    children: list[dict[str, Any]] = []

    for d in dirs:
        child_node, sub_dir_count, sub_file_count = _build_workspace_tree_node(d, root)
        children.append(child_node)
        dir_count += 1 + sub_dir_count
        file_count += sub_file_count

    for f in files:
        file_count += 1
        rel_file = str(f.relative_to(root)).replace("\\", "/")
        size = 0
        try:
            size = f.stat().st_size if f.exists() else 0
        except Exception:
            size = 0
        children.append(
            {
                "name": f.name,
                "relativePath": rel_file,
                "filePath": str(f),
                "type": "file",
                "size": size,
            }
        )


    node["children"] = children
    node["dirCount"] = dir_count
    node["fileCount"] = file_count
    return node, dir_count, file_count


@router.get("/local/workspace-files")
def workspace_files_api(cwd: str = Query(default="")) -> dict[str, Any]:
    root = _existing_path(cwd)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="工作目录不是文件夹")

    tree, dir_count, file_count = _build_workspace_tree_node(root, root)
    return {
        "cwd": str(root),
        "dirCount": dir_count,
        "fileCount": file_count,
        "tree": tree,
    }


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

