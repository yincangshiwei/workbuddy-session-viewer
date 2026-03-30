from __future__ import annotations

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

