import html
import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.routes.integrations.adora import adora_router
from api.routes.integrations.shopify import _implementation
from api.routes.integrations.square import _implementation as square_implementation
from api.routes.integrations.toast import toast_router
from api.routes.integrations.vapi import vapi_router
from api.schemas.chat.chat import ChatInfo, ChatRequest, ChatResponse
from api.schemas.error.error import ErrorResponse

integrations_router = APIRouter(prefix=endpoints.INTEGRATIONS, tags=["Integrations"])

# Include the VAPI router
integrations_router.include_router(vapi_router)

# Include the Adora router
integrations_router.include_router(adora_router)

# Include the Toast router
integrations_router.include_router(toast_router)


@integrations_router.get("/shopify/{app_name}/install", status_code=status.HTTP_200_OK)
async def install(request: Request, app_name: str):
    """
    Redirects to the installation page for the integration.
    """
    return await _implementation.install(request, html.escape(app_name))


@integrations_router.get("/shopify/{app_name}/callback", status_code=status.HTTP_200_OK)
async def callback(request: Request, app_name: str):
    """
    Handles the callback from the integration.
    """
    return await _implementation.callback(request, html.escape(app_name))


@integrations_router.post(
    "/shopify/{app_name}/chat",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(
    chat_request: ChatRequest,
    request: Request,
    app_name: str,
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    There is no need to obtain the identifier or the store name from the request, the api_chat will handle it.
    the request_url from the widget likes: https://STORE_NAME.myshopify.com/apps/APP_NAME/chat, the STORE_NAME can be pal-chatbot, and the APP_NAME can be Palona or some other customized apps for our clients. The Shopify app enables the app proxy which points the request_url to https://api.palona.ai/v1/integrations/shopify/APP_NAME/chat, the APP_NAME is the same as the one in the request_url.

    The Shopify app will sign the request and send it to the request_url. The api_chat will validate the request and get the ShopifyStore object. The ShopifyStore object contains the shop_url, session, app_name, store_name, and recipient_identifier. It can be trusted if the request is valid. As the Shopify side verifies and signs the request. We don't need to let the Shopify widget to explicitly send the apikey or identifier in the request. This will secure our apikey and identifier.
    """

    return await _implementation.api_chat(
        chat_request, request, html.escape(app_name), session
    )


@integrations_router.get("/shopify/{app_name}/chat/info")
def get_project_info(
    request: Request,
    app_name: str,
    session: Session = Depends(db.get_db),
) -> ChatInfo:
    return _implementation.api_project_info(
        request,
        html.escape(app_name),
        session,
    )


@integrations_router.get("/square/install", status_code=status.HTTP_200_OK)
async def square_install(request: Request):
    """
    Redirects to the Square OAuth installation page for the integration.
    """
    return await square_implementation.install(request)


@integrations_router.get("/square/callback", status_code=status.HTTP_200_OK)
async def square_callback(request: Request):
    """
    Handles the callback from Square OAuth.
    """
    return await square_implementation.callback(request)


@integrations_router.post("/square/refresh-expiring", status_code=status.HTTP_200_OK)
@integrations_router.get("/square/refresh-expiring", status_code=status.HTTP_200_OK)
async def square_refresh_expiring(session=Depends(db.get_db)):
    """
    Check all Square integrations and refresh tokens that are expiring within 7 days.
    """
    try:
        result = square_implementation.check_and_refresh_expiring_square_tokens(
            session=session, days_threshold=7
        )
        return result
    finally:
        session.close()


@integrations_router.get(
    "/square/{account_name}/{integration_id}/locations", status_code=status.HTTP_200_OK
)
async def get_square_locations(account_name: str, integration_id: uuid.UUID):
    """
    Get all locations for a Square merchant.

    Args:
        account_name: Name of the account
        integration_id: UUID of the Square integration

    Returns:
        List of locations for the merchant
    """
    session = next(db.get_db())
    try:
        result = square_implementation.get_merchant_locations(
            session=session, account_name=account_name, integration_id=integration_id
        )
        return result
    finally:
        session.close()
