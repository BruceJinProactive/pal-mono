from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from ._implementation import handle_stripe_webhook

stripe_router = APIRouter(prefix="/stripe", tags=["Integrations"])


@stripe_router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Webhook processed successfully"},
        400: {"description": "Invalid signature or payload"},
        500: {"description": "Internal server error"},
    },
)
async def stripe_webhook(request: Request) -> dict[str, str]:
    """
    Handle incoming Stripe webhook events for billing notifications.

    Supported events:
    - invoice.payment_failed: Triggered when payment fails
    - invoice.payment_succeeded: Triggered when payment succeeds

    The webhook verifies the Stripe signature and maps the customer to an account
    before sending billing notification emails.

    Args:
        request: FastAPI request containing webhook payload and signature header

    Returns:
        JSON response with status

    Raises:
        HTTPException: 400 if signature is invalid, 500 on processing error
    """
    return await handle_stripe_webhook(request)
