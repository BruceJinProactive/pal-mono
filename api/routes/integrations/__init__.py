import html

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.routes.integrations.shopify import _implementation
from api.schemas.chat.chat import ChatInfo, ChatRequest, ChatResponse
from api.schemas.error.error import ErrorResponse

integrations_router = APIRouter(prefix=endpoints.INTEGRATIONS, tags=["Integrations"])


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
