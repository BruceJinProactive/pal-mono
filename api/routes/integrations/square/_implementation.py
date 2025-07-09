import os
import binascii
import requests

from fastapi import Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from ._util import set_access_token, get_square_client_id, get_square_client_secret
from ._valid import _oauth_state, valid_request
from services.service_utils import get_server_url

SQUARE_AUTH_URL = "https://connect.squareup.com/oauth2/authorize"
SQUARE_TOKEN_URL = "https://connect.squareup.com/oauth2/token"
SQUARE_SCOPES = ["PAYMENTS_READ", "CUSTOMERS_READ"]


async def install(request: Request, app_name: str):
    # Generate state for CSRF protection
    state = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
    _oauth_state[state] = True  # No shop_url needed for Square

    client_id = get_square_client_id(app_name)
    scopes = " ".join(SQUARE_SCOPES)
    # Build the redirect URI dynamically
    redirect_uri = f"{get_server_url()}/v1/integrations/square/{app_name}/callback"
    auth_url = (
        f"{SQUARE_AUTH_URL}?client_id={client_id}"
        f"&scope={scopes}"
        f"&session=False"
        f"&state={state}"
        f"&redirect_uri={redirect_uri}"
    )
    return RedirectResponse(auth_url)


async def callback(request: Request, app_name: str):
    # Validate state parameter for CSRF protection
    valid_request(request, app_name, is_callback=True)
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    # Validate state
    if not state or state not in _oauth_state:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid or missing state parameter"},
        )
    del _oauth_state[state]  # Remove state after use

    if not code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing authorization code"},
        )

    try:
        client_id = get_square_client_id(app_name)
        client_secret = get_square_client_secret(app_name)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(e)},
        )
    # Always build the redirect_uri dynamically for token exchange
    redirect_uri = f"{get_server_url()}/v1/integrations/square/{app_name}/callback"

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
    merchant_id = token_data.get("merchant_id")
    # print(
    #    f"[DEBUG] Access token: {access_token}"
    # )  # <--- This will print the token in your terminal

    if not access_token or not merchant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing access token or merchant ID in response"},
        )

    token_prefix = f"{app_name}_{merchant_id}"
    try:
        set_access_token(token_prefix, access_token)
    except Exception as e:
        print(f"[DEBUG] Failed to store access token: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal Token Error"},
        )

    # Optionally, redirect to a success page or just return a message
    return JSONResponse(
        {"message": "Access token stored successfully!", "merchant_id": merchant_id}
    )


# TODO: Implement api_chat and api_project_info if needed for Square, similar to Shopify
