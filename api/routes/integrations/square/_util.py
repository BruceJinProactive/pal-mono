import os
import json
from utils import secret
from utils.log import logger


def get_square_client_id(app_name: str) -> str:
    value = secret._get_client_secrets().get(
        f"SQUARE_{app_name.upper()}_CLIENT_ID"
    ) or os.getenv(f"SQUARE_{app_name.upper()}_CLIENT_ID")
    if value is None:
        raise ValueError(
            f"SQUARE_{app_name.upper()}_CLIENT_ID is not set in secrets or environment variables"
        )
    return value


def get_square_client_secret(app_name: str) -> str:
    value = secret._get_client_secrets().get(
        f"SQUARE_{app_name.upper()}_CLIENT_SECRET"
    ) or os.getenv(f"SQUARE_{app_name.upper()}_CLIENT_SECRET")
    if value is None:
        raise ValueError(
            f"SQUARE_{app_name.upper()}_CLIENT_SECRET is not set in secrets or environment variables"
        )
    return value


def set_access_token(token_prefix: str, access_token: str) -> None:
    # print(f"[DEBUG] Storing access token for {token_prefix}: {access_token}")
    project_secret_key = f"{token_prefix.upper()}_SQUARE_ACCESS_TOKEN"
    project_secret_value = json.dumps({"access_token": access_token})
    try:
        secret.upsert_client_secret(project_secret_key, project_secret_value)
    except Exception as e:
        logger.error(f"Unable to set {token_prefix} access token: {e}")
        raise RuntimeError(f"Unable to set {token_prefix} access token: {e}")
