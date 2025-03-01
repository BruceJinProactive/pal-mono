import binascii
import os

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ._util import get_shopify_session, set_access_token

_DEFAULT_SCOPES = ["read_products", "write_products", "read_orders", "write_orders"]
_app_prefix_map = {
    "windsor": "PALONA_WINDSOR",  # production version of widnsor
    "palona": "PALONA",  # production verison of palona
    "palona_dev": "PALONA_DEV",  # dev verison of palona
    "palona_single_test": "PALONA_SINGLE_TEST",  # identical to windsor
    "palona_single_local": "PALONA_SINGLE_LOCAL",  # for local testing
}  # app name to Shopify API prefix
_app_callback_map = {
    "windsor": "https://stg-api.proactiveailab.com/v1/integrations/shopify/windsor/callback",
    "palona_single_test": "https://lat-api.proactiveailab.com/v1/integrations/shopify/palona_single_test/callback",
    "palona_single_local": "http://b1rdkt5cpa.execute-api.us-west-1.amazonaws.com:8000/v1/integrations/shopify/palona_single_local/callback",
}  # app name to callback url
_app_project_map = {
    "windsor": "windsor-default"
}  # app name to project_name which is for the prefix of AWS secrets manager
_oauth_state = {}


def _valid_request(request: Request, app_name: str, is_callback=False):
    # valid the app name
    if app_name not in _app_prefix_map:
        raise HTTPException(status_code=404, detail="App not found.")
    shop_url = request.query_params.get("shop")

    # check the shop url
    if not shop_url:
        raise HTTPException(status_code=400, detail="Missing 'shop' parameter")

    if is_callback:
        state = request.query_params.get("state")
        if state not in _oauth_state:
            raise HTTPException(
                status_code=400, detail="Invalid Request: Missing State"
            )
        if _oauth_state[state] != shop_url:
            raise HTTPException(
                status_code=400, detail="Invalid Request: Invalid State"
            )
        del _oauth_state[state]

    app_prefix = _app_prefix_map[app_name]
    session = get_shopify_session(shop_url, app_prefix)

    # validate the oauth request
    try:
        if not session.validate_params(dict(request.query_params)):
            raise HTTPException(
                status_code=400, detail="Invalid Request: Invalid Params"
            )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid API Key")
    return shop_url, session, app_prefix


async def install(request: Request, app_name: str):
    shop_url, session, _ = _valid_request(request, app_name)

    # check the embedded param, if 1 then return the successful template
    embedded = request.query_params.get("embedded", "0")
    if embedded != "0":
        return JSONResponse(status_code=200, content={"Success": "Welcome to Palona!"})

    # save the state to prevent CSRF attack
    state = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
    _oauth_state[state] = shop_url

    # build the auth request
    try:
        redirect_uri = _app_callback_map[app_name]
    except KeyError:
        raise HTTPException(status_code=404, detail="Missing Callback URL")
    scopes = _DEFAULT_SCOPES  # os.getenv(f"SHOPIFY_{app_prefix}_SCOPES", _DEFAULT_SCOPES).split(",")
    auth_url = session.create_permission_url(scopes, redirect_uri, state)
    return RedirectResponse(auth_url)


async def callback(request: Request, app_name: str):

    # validate the request
    shop_url, session, app_prefix = _valid_request(request, app_name, is_callback=True)
    store_name = shop_url.split(".myshopify.com")[0]  # windsor-us

    # get the access token
    try:
        access_token = session.request_token(dict(request.query_params))
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid Request: Failed to get Access Token"},
        )

    # set the access token
    project_name: str = _app_project_map.get(app_name, "windsor-default")
    try:
        set_access_token(None, None, project_name, access_token)
    except Exception:
        return JSONResponse(status_code=500, content={"error": "Internal Error"})

    # redirect to https://admin.shopify.com/store/windsor-us/apps/palona_windsor after successfull installed
    return RedirectResponse(
        url=f"https://admin.shopify.com/store/{store_name}/apps/{app_prefix.lower()}"
    )
