from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.delete import router as delete_router
from app.api.routes.health import router as health_router
from app.api.routes.local_files import router as local_files_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.transfer import router as transfer_router


api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(transfer_router)
api_router.include_router(local_files_router)
api_router.include_router(delete_router)

