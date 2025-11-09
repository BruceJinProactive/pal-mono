from fastapi import APIRouter

from .events import events_router

internal_router = APIRouter(prefix="/internal", tags=["internal"])
internal_router.include_router(events_router)
