import json
import os
import uuid
from typing import Optional

import shopify
from sqlalchemy.orm import Session

from services.project_service import get_project
from utils import secret
from utils.log import logger


def _get_envs_from_secret_manager(merchant: str) -> dict:
    """
    Get the environment variables for a given merchant.
    Args:
        merchant (str): The merchant for which the environment variables are to be retrieved.
    Returns:
        dict: The environment variables for the given merchant
    """
    merchant = merchant.upper()
    app_secrets = secret._get_client_secrets()
    return {
        "SHOPIFY_API_KEY": app_secrets.get(f"SHOPIFY_{merchant}_API_KEY"),
        "SHOPIFY_API_SECRET": app_secrets.get(f"SHOPIFY_{merchant}_API_SECRET"),
        "SHOPIFY_API_VER": os.getenv(f"SHOPIFY_{merchant}_API_VER", "2025-01"),
    }


def get_shopify_session(shop_url: str, merchant: str) -> shopify.Session:
    """Get a Shopify session for a given merchant.
    Args:
        shop_url (str): The URL of the Shopify store.
        merchant (str): The merchant for which the session is to be retrieved.
    Returns:
        shopify.Session: The Shopify session for the given merchant.
    """
    store_envs = _get_envs_from_secret_manager(merchant)
    session = shopify.Session(shop_url, store_envs["SHOPIFY_API_VER"])
    session.setup(
        api_key=store_envs["SHOPIFY_API_KEY"], secret=store_envs["SHOPIFY_API_SECRET"]
    )
    return session


def set_access_token(
    session: Optional[Session],
    project_id: Optional[uuid.UUID],
    project_name: str,
    access_token: str,
) -> None:
    """
    Add shopify access token to the secret store.
    Args:
        session (Session): The database connection.
        project_id (uuid.UUID): The unique identifier of the project.
        access_token (str): The access token to be stored.
    """
    if project_name is None and project_id is None:
        raise ValueError("Either project_name or project_id must be provided.")
    if project_id is not None and session is not None:
        project = get_project(
            session, project_id
        )  # TODO: how to manage proj? windsor-default
        if not project:
            raise ValueError("Project not found.")
        project_name = project.name
    project_secret_key = _project_name_to_shopify_access_token_key(project_name)
    project_secret_value = json.dumps({"access_token": access_token})

    # Add secrets, and rollback if necessary
    try:
        # Attempt to add both secrets one by one
        secret.upsert_client_secret(project_secret_key, project_secret_value)
    except Exception as e:
        logger.error(f"Unable to set {project_name} access token: {e}")
        raise RuntimeError(f"Unable to set {project_name} access token: {e}")


def _project_name_to_shopify_access_token_key(project_name: str) -> str:
    """
    Convert a project name to the key used to store the Shopify access token in the secret store.
    Args:
        project_name (str): The name of the project.
    Returns:
        str: The key used to store the Shopify access token in the secret store.
    """
    return f"{project_name.upper()}_SHOPIFY_ACCESS_TOKEN"
