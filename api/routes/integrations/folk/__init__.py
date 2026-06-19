from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from api.schemas.error.error import ErrorResponse
from services.folk_notion_sync._service import process_folk_event
from services.folk_notion_sync._settings import get_folk_notion_sync_settings
from services.folk_notion_sync._webhook import (
    parse_folk_webhook_event,
    verify_folk_webhook_signature,
)
from utils.log import logger
from utils.secret import get_server_secret_with_fallback

folk_router = APIRouter(prefix="/folk", tags=["Integrations"])


@folk_router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Webhook accepted"},
        400: {"description": "Invalid signature or payload", "model": ErrorResponse},
        500: {
            "description": "Webhook secret not configured",
            "model": ErrorResponse,
        },
    },
)
async def folk_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    body = await request.body()
    settings = get_folk_notion_sync_settings()
    if not settings.enabled:
        return {"status": "disabled"}

    try:
        signing_secret = get_server_secret_with_fallback("FOLK_WEBHOOK_SIGNING_SECRET")
    except ValueError as exc:
        logger.error("[FolkNotionSync] FOLK_WEBHOOK_SIGNING_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Folk webhook signing secret not configured",
            headers={"Content-Type": "application/json"},
        ) from exc

    if not verify_folk_webhook_signature(body, request.headers, signing_secret):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Folk webhook signature",
            headers={"Content-Type": "application/json"},
        )

    try:
        event = parse_folk_webhook_event(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers={"Content-Type": "application/json"},
        ) from exc

    # Folk can redeliver events; this MVP relies on Notion matching for
    # idempotency until there is a durable processed-event store.
    background_tasks.add_task(process_folk_event, event, settings=settings)
    return {"status": "accepted"}
