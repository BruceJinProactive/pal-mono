import json
import os

from utils import secret
from utils.log import logger


def get_square_client_id() -> str:
    value = secret._get_client_secrets().get("SQUARE_CLIENT_ID") or os.getenv(
        "SQUARE_CLIENT_ID"
    )
    if value is None:
        raise ValueError(
            "SQUARE_CLIENT_ID is not set in secrets or environment variables"
        )
    return value


def get_square_client_secret() -> str:
    value = secret._get_client_secrets().get("SQUARE_CLIENT_SECRET") or os.getenv(
        "SQUARE_CLIENT_SECRET"
    )
    if value is None:
        raise ValueError(
            "SQUARE_CLIENT_SECRET is not set in secrets or environment variables"
        )
    return value


def set_access_token(token_prefix: str, access_token: str, refresh_token: str) -> None:
    project_secret_key = f"{token_prefix.upper()}_TOKENS"
    token_data = {"access_token": access_token, "refresh_token": refresh_token}
    project_secret_value = json.dumps(token_data)
    try:
        secret.upsert_client_secret(project_secret_key, project_secret_value)
    except Exception as e:
        logger.error(f"Unable to set {token_prefix} access token: {e}")
        raise RuntimeError(f"Unable to set {token_prefix} access token: {e}")
