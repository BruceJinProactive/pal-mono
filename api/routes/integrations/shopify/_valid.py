import hashlib
import hmac
import html

from fastapi import HTTPException, Request, status

from utils.log import logger

from ._util import ShopifyStore, get_recipient_identifier, get_shopify_session

# app names in Shopify: https://partners.shopify.com/4092807/apps
_app_name_whitelist = {
    "palona_windsor": "",  # app name of the production version of windsor
    "palona": "",  # app name of the production version of palona
    "palona_dev": "",  # app name of the dev version of palona
    "palona_single_test": "",  # for local testing
}  # app name to Shopify API prefix

_oauth_state = {}


def valid_proxy_request(valid_dict, secret, signature):
    sorted_params = "".join(f"{k}={valid_dict[k]}" for k in sorted(valid_dict))
    calculated_signature = hmac.new(
        secret.encode("utf-8"),
        sorted_params.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, calculated_signature)


def valid_request(request: Request, app_name: str, is_callback=False) -> ShopifyStore:
    """
    This module contains the functions to validate the request and get the ShopifyStore object.
    The shopifyStore object contains the shop_url, session, app_name, store_name, and recipient_identifier.
    It can be trusted if the request is valid. As the Shopify side verifies and signs the request. We don't need to let the Shopify widget to explicitly send the apikey or identifier in the request. This will secure our apikey and identifier.
    """

    # valid the app name
    if app_name.lower() not in _app_name_whitelist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found."
        )
    shop_url = request.query_params.get("shop")

    # check the shop url
    if not shop_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'shop' parameter"
        )
    shop_url = html.escape(shop_url)
    store_name = shop_url.split(".myshopify.com")[0]
    if is_callback:
        state = request.query_params.get("state")
        if state not in _oauth_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Request: Missing State",
            )
        if _oauth_state[state] != shop_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Request: Invalid State",
            )
        del _oauth_state[state]

    session = get_shopify_session(shop_url, app_name)

    # validate the oauth request

    valid_dict = dict(request.query_params)
    logged_in_customer_id = valid_dict.get("logged_in_customer_id", None)

    # this is for the shopify app proxy: https://shopify.dev/docs/apps/build/online-store/display-dynamic-data
    if "signature" in valid_dict and "hmac" not in valid_dict:
        signature = valid_dict.pop("signature")
        if not valid_proxy_request(valid_dict, session.secret, signature):
            logger.error(f"Invalid OAuth Request: {request.query_params}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Request: Invalid Proxy Signature",
            )
    else:
        if not session.validate_params(valid_dict):
            logger.error(f"Invalid Oauth Request: {request.query_params}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Request: Invalid Params",
            )
    shopifyStore = ShopifyStore(
        shop_url,
        session,
        app_name,
        store_name,
        get_recipient_identifier(store_name),
        logged_in_customer_id,
    )
    return shopifyStore
