from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeleteRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class PathActionRequest(BaseModel):
    path: str = ""


class DeleteResponse(BaseModel):
    success: bool
    dbDeleted: int = 0
    filesDeleted: int = 0
    deletedFiles: list[str] = Field(default_factory=list)


class RestoreRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class RestoreResponse(BaseModel):
    success: bool
    restored: int = 0


class UpdateTitleRequest(BaseModel):
    title: str


class WorkspaceDeleteRequest(BaseModel):
    cwd: str


class ModelsConfigSaveRequest(BaseModel):
    models: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] | None = None


