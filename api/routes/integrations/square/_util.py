import os

from utils import secret


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
