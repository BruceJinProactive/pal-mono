import json
import os

import shopify

from utils import secret
from utils.log import logger

# from ._util_debug import _get_envs as _get_envs_from_secret_manager


def _get_envs_from_secret_manager(app_name: str) -> dict:
    """
    Get the environment variables for a given merchant.
    Args:
        merchant (str): The merchant for which the environment variables are to be retrieved.
    Returns:
        dict: The environment variables for the given merchant
    """
    app_secrets = secret._get_client_secrets()
    return {
        "SHOPIFY_API_KEY": app_secrets.get(f"SHOPIFY_{app_name.upper()}_API_KEY"),
        "SHOPIFY_API_SECRET": app_secrets.get(f"SHOPIFY_{app_name.upper()}_API_SECRET"),
        "SHOPIFY_API_VER": os.getenv(f"SHOPIFY_{app_name.upper()}_API_VER", "2025-01"),
    }


class ShopifyStore:
    # shop_url, session, app_name, store_name, get_identifier_name(store_name)
    def __init__(self, shop_url, session, app_name, store_name, recipient_identifier):
        self.shop_url = shop_url
        self.session = session
        self.app_name = app_name
        self.store_name = store_name
        self.recipient_identifier = recipient_identifier


def get_identifier_name(store_name: str) -> str:
    identifier_name: str = "shopify-" + store_name
    return identifier_name


def get_shopify_session(shop_url: str, app_name: str) -> shopify.Session:
    """Get a Shopify session for a given merchant.
    Args:
        shop_url (str): The URL of the Shopify store.
        merchant (str): The merchant for which the session is to be retrieved.
    Returns:
        shopify.Session: The Shopify session for the given merchant.
    """
    app_envs = _get_envs_from_secret_manager(app_name)
    session = shopify.Session(shop_url, app_envs["SHOPIFY_API_VER"])
    session.setup(
        api_key=app_envs["SHOPIFY_API_KEY"], secret=app_envs["SHOPIFY_API_SECRET"]
    )
    return session


def set_access_token(
    token_prefix: str,
    access_token: str,
) -> None:

    project_secret_key = _project_name_to_shopify_access_token_key(token_prefix)
    project_secret_value = json.dumps({"access_token": access_token})

    # Add secrets, and rollback if necessary
    try:
        # Attempt to add both secrets one by one
        secret.upsert_client_secret(project_secret_key, project_secret_value)
    except Exception as e:
        logger.error(f"Unable to set {token_prefix} access token: {e}")
        raise RuntimeError(f"Unable to set {token_prefix} access token: {e}")


def _project_name_to_shopify_access_token_key(token_prefix: str) -> str:
    """
    Convert a project name to the key used to store the Shopify access token in the secret store.
    Args:
        project_name (str): The name of the project.
    Returns:
        str: The key used to store the Shopify access token in the secret store.
    """
    return f"{token_prefix.upper()}_SHOPIFY_ACCESS_TOKEN"
