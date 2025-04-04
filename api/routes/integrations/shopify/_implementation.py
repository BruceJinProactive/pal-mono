import binascii
import os

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from api.routes.chat.chat import chat, get_project_info
from api.schemas.chat.chat import ChatRequest
from utils.log import logger

from ._util import set_access_token
from ._valid import _oauth_state, valid_request

_DEFAULT_SCOPES = ["read_products", "read_orders", "read_customers"]

shopify_callback_maps = {
    "lat": "https://lat-api.palona.ai/v1/integrations/shopify",
    "stg": "https://stg-api.palona.ai/v1/integrations/shopify",
    "prd": "https://api.palona.ai/v1/integrations/shopify",
    "dev": "http://dev-api.palona.ai:8000/v1/integrations/shopify",
}


async def install(request: Request, app_name: str):
    stage = os.environ.get("RUNTIME_ENV", "prd")
    shopifyStore = valid_request(request, app_name)
    shop_url, session = shopifyStore.shop_url, shopifyStore.session
    # check the embedded param, if 1 then return the successful template
    embedded = request.query_params.get("embedded", "0")
    if embedded != "0":
        # return JSONResponse(
        #     status_code=status.HTTP_200_OK, content={"Success": "Welcome to Palona!"}
        # )
        return RedirectResponse(
            url=f"https://console.palona.ai/?shop={shop_url}&app={app_name}"
        )

    # save the state to prevent CSRF attack
    state = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
    _oauth_state[state] = shop_url

    # build the auth request
    try:
        redirect_uri = f"{shopify_callback_maps[stage]}/{app_name}/callback"
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Missing Callback URL"
        )
    scopes = _DEFAULT_SCOPES  # os.getenv(f"SHOPIFY_{app_prefix}_SCOPES", _DEFAULT_SCOPES).split(",")
    auth_url = session.create_permission_url(scopes, redirect_uri, state)
    return RedirectResponse(auth_url)


async def callback(request: Request, app_name: str):
    # validate the request
    shopifyStore = valid_request(request, app_name)
    session, store_name, identifier_name = (
        shopifyStore.session,
        shopifyStore.store_name,
        shopifyStore.recipient_identifier,  # identifier_name: palona-default, windsor-us-default. ${store_name}-default.
    )

    # get the access token
    try:
        access_token = session.request_token(dict(request.query_params))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid Request: Failed to get Access Token"},
        )

    token_prefix = f"{app_name}_{identifier_name}"  # app_name, identifier_name,
    try:
        set_access_token(token_prefix, access_token)
    except Exception:
        logger.error(f"Unable to set {token_prefix} access token:{access_token}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal Token Error"},
        )

    # redirect to https://admin.shopify.com/store/windsor-us/apps/palona_windsor after successfull installed
    return RedirectResponse(
        url=f"https://admin.shopify.com/store/{store_name}/apps/{app_name}"
    )


async def api_chat(
    chat_request: ChatRequest, request: Request, app_name: str, session: AsyncSession
):
    shopifyStore = valid_request(request, app_name)
    # make sure the indentifer is identical to the store name, the store name can be trusted if the valid_request is true; the browser won't need to send the store name and the apikey in the request.
    chat_request.message.recipient_identifier = shopifyStore.recipient_identifier
    return await chat(chat_request, session)


def api_project_info(
    request: Request,
    app_name: str,
    session: Session,
):
    shopifyStore = valid_request(request, app_name)
    return get_project_info(
        request,
        shopifyStore.store_name,
        session,
    )
