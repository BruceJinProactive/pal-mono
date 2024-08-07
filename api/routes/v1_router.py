from fastapi import APIRouter

from api.routes.admin import admin_router
from api.routes.assistants import assistants_router
from api.routes.chat import chat_router
from api.routes.sendblue import sendblue_router
from api.routes.status import status_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(admin_router)
v1_router.include_router(assistants_router)
v1_router.include_router(chat_router)
v1_router.include_router(sendblue_router)
v1_router.include_router(status_router)
