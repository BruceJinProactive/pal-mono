import binascii
import os

import requests
from fastapi import Request, status
from fastapi.responses import JSONResponse, RedirectResponse

import db
from api.routes.admin._auth import authenticate_user, authorize_user_account
from api.schemas.admin.integration import IntegrationRequest
from db.tables.types import IntegrationProvider, IntegrationType, AuthType
from services.integration_service import create_integration
from services.integration_service.schema import IntegrationParams
from services.service_utils import get_server_url
from utils.log import logger

from ._util import get_square_client_id, get_square_client_secret, set_access_token
from ._valid import _oauth_state, valid_request


SQUARE_AUTH_URL = "https://connect.squareup.com/oauth2/authorize"
SQUARE_TOKEN_URL = "https://connect.squareup.com/oauth2/token"
SQUARE_SCOPES = ["ITEMS_READ", "ORDERS_READ", "ORDERS_WRITE"]


async def install(request: Request):
    account_name = request.query_params.get("account_name")
    if not account_name:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "account_name parameter is required"},
        )

    # Generate state for CSRF protection and store account context
    state = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
    _oauth_state[state] = account_name

    client_id = get_square_client_id()
    scopes = " ".join(SQUARE_SCOPES)
    # Build the redirect URI dynamically
    redirect_uri = f"{get_server_url()}/v1/integrations/square/callback"
    auth_url = (
        f"{SQUARE_AUTH_URL}?client_id={client_id}"
        f"&scope={scopes}"
        f"&session=False"
        f"&state={state}"
        f"&redirect_uri={redirect_uri}"
    )
    return RedirectResponse(auth_url)


async def callback(request: Request):
    # Validate state parameter for CSRF protection and get account_name
    account_name_result = valid_request(request, is_callback=True)
    if not isinstance(account_name_result, str):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid state validation"},
        )
    account_name = account_name_result

    code = request.query_params.get("code")

    if not code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing authorization code"},
        )

    try:
        client_id = get_square_client_id()
        client_secret = get_square_client_secret()
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(e)},
        )

    # Always build the redirect_uri dynamically for token exchange
    redirect_uri = f"{get_server_url()}/v1/integrations/square/callback"

    # Exchange code for access token
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(SQUARE_TOKEN_URL, json=data, headers=headers)
    if resp.status_code != 200:
        print(f"[DEBUG] Token exchange failed: {resp.text}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Failed to exchange code for token",
                "details": resp.text,
            },
        )
    token_data = resp.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    merchant_id = token_data.get("merchant_id")

    if not access_token or not refresh_token or not merchant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Missing access token, refresh token, or merchant ID in response"
            },
        )

    try:
        context = authenticate_user(request)
        authorize_user_account(context, account_name)

        session = next(db.get_db())
        try:
            account_repository = db.AccountRepository(session)
            account = account_repository.get_account(account_name)
            if not account:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": f"Account {account_name} not found"},
                )

            integration_request = IntegrationParams(
                provider=IntegrationProvider.square,
                integration_type=IntegrationType.pos,
                auth_type=AuthType.oauth,
                business_id=merchant_id,
                access_token=access_token,
                refresh_token=refresh_token,
                client_id=None,
                client_secret=None,
                api_key=None,
            )

            created_integration = create_integration(
                session=session,
                account_id=account.id,
                params=integration_request,
            )

            return JSONResponse(
                {
                    "message": "Integration created successfully!",
                    "merchant_id": merchant_id,
                    "integration_id": str(created_integration.id),
                }
            )
        finally:
            session.close()

    except Exception as e:
        logger.error(f"[DEBUG] Failed to create integration: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Failed to create integration: {e}"},
        )


# TODO: Implement api_chat and api_project_info if needed for Square, similar to Shopify
