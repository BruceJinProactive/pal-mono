import json

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from db.tables import Integration, IntegrationProvider
from tools.toast_tool._apis import get_dining_options
from tools.toast_tool._utils import get_toast_access_token_from_aws
from tools.toast_tool.classes import DiningBehavior
from utils.log import logger

from ._utils import (
    process_partner_event,
    update_menu_content,
    update_ordering_schedule,
    update_stock_item_status,
)
from .schema import ToastWebhookRequest, ToastWebhookResponse


async def api_toast_webhook(request: Request) -> JSONResponse:
    """
    Process incoming webhook requests from Toast.
    Authentication and validation are handled by AWS API Gateway.

    Args:
        request: The FastAPI request object

    Returns:
        JSONResponse: The response to send back to Toast

    Raises:
        HTTPException: If there's an error processing the request
    """
    # Extract body from request
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid JSON in request body: {str(e)}"},
        )

    # Validate request body against schema
    try:
        webhook_request = ToastWebhookRequest(**body)

        # Handle webhook events
        match webhook_request.eventCategory:
            case "menus":
                await update_menu_content(webhook_request)
            case "stock":
                await update_stock_item_status(webhook_request)
            case "ordering_schedule":
                await update_ordering_schedule(webhook_request)
            case "partner":
                await process_partner_event(webhook_request)
            case _:
                logger.warning(
                    f"[ToastWebhook.api_toast_webhook] Received unknown Toast webhook event category: {webhook_request.eventCategory}"
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=ToastWebhookResponse().model_dump(exclude_none=True),
                )
    except ValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid request body: {str(e)}"},
        )

    # Log the incoming request for debugging
    logger.debug(
        "[ToastWebhook.api_toast_webhook] Toast webhook request received",
        extra={
            "timestamp": webhook_request.timestamp,
            "event_category": webhook_request.eventCategory,
            "event_type": webhook_request.eventType,
            "guid": webhook_request.guid,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ToastWebhookResponse().model_dump(exclude_none=True),
    )


def check_and_refresh_dining_options(session):
    """
    Check all Toast integrations and check if take out dining option is available. Refresh project with take out dining option UUID if not already set or the UUID is different.
    """
    # Get all integrations whose integration provider is toast
    integrations = (
        session.query(Integration)
        .filter(Integration.provider == IntegrationProvider.toast)
        .all()
    )

    # Get bearer token from access token
    bearer_token = get_toast_access_token_from_aws()

    # Iterate over each integration and get dining options for each store
    store_with_take_out_dining_option = set()
    store_without_take_out_dining_option = set()

    for integration in integrations:
        if not integration.business_id:
            logger.warning(
                "[ToastWebhook.check_and_refresh_dining_options] Integration has no business ID, skipping"
            )
            continue
        try:
            dining_options = get_dining_options(
                bearer_token=bearer_token,
                store_id=integration.business_id,
            )
        except Exception as e:
            logger.warning(
                "[ToastWebhook.check_and_refresh_dining_options] Failed to fetch dining options for store %s (error=%s)",
                integration.business_id,
                e.__class__.__name__,
                exc_info=True,
            )
            store_without_take_out_dining_option.add(integration.business_id)
            continue

        # Check if take out dining option is available
        take_out_dining_option = next(
            (
                option
                for option in dining_options
                if option.behavior == DiningBehavior.TAKE_OUT
            ),
            None,
        )
        if not take_out_dining_option:
            logger.warning(
                "[ToastWebhook.check_and_refresh_dining_options] Take out dining option is not available, skipping"
            )
            store_without_take_out_dining_option.add(integration.business_id)

        else:
            store_with_take_out_dining_option.add(integration.business_id)

        # TODO: Update project with take out dining option UUID if not already set or the UUID is different

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "Dining options successfully checked",
            "store_with_take_out_dining_option": list(
                store_with_take_out_dining_option
            ),
            "store_without_take_out_dining_option": list(
                store_without_take_out_dining_option
            ),
        },
    )
