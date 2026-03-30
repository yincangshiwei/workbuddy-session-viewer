from fastapi import APIRouter, HTTPException

from app.schemas.session import DeleteRequest, DeleteResponse
from app.services.delete_service import delete_local_files, delete_sessions

router = APIRouter()


@router.post("/delete", response_model=DeleteResponse)
def delete_api(payload: DeleteRequest) -> DeleteResponse:
    ids = [x for x in payload.ids if x]
    if not ids:
        raise HTTPException(status_code=400, detail="ids required")

    db_deleted = delete_sessions(ids)
    deleted_files = delete_local_files(ids)
    return DeleteResponse(
        success=True,
        dbDeleted=db_deleted,
        filesDeleted=len(deleted_files),
        deletedFiles=deleted_files,
    )
