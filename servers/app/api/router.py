from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.chat import router as chat_router
from app.api.routes.delete import router as delete_router
from app.api.routes.health import router as health_router
from app.api.routes.local_files import router as local_files_router
from app.api.routes.model_config import router as model_config_router
from app.api.routes.restore import router as restore_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.transfer import router as transfer_router
from app.api.routes.title import router as title_router
from app.api.routes.workspaces import router as workspaces_router


api_router = APIRouter(prefix="/api")
api_router.include_router(admin_router)
api_router.include_router(health_router)
api_router.include_router(sessions_router)
api_router.include_router(chat_router)
api_router.include_router(transfer_router)
api_router.include_router(local_files_router)
api_router.include_router(model_config_router)
api_router.include_router(delete_router)
api_router.include_router(restore_router)
api_router.include_router(title_router)
api_router.include_router(workspaces_router)


