from fastapi import APIRouter

from api.routes.admin import admin_router
from api.routes.asset import asset_router
from api.routes.chat.chat import chat_router
from api.routes.status import status_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(admin_router)
v1_router.include_router(chat_router)
v1_router.include_router(status_router)
v1_router.include_router(asset_router)
