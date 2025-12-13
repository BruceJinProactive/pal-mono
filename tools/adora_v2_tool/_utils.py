import re

from utils.log import logger
from utils.secret import get_client_secret_with_fallback


def get_adora_credentials(account_name: str) -> tuple[str | None, str | None]:
    """Fetch Adora API credentials from AWS Secrets Manager."""
    if not account_name:
        logger.error("[AdoraV2Tool._utils] account_name is missing")
        return None, None

    try:
        name = re.sub(r"[^a-zA-Z0-9]", "", account_name).upper()
        if not name:
            logger.error(
                f"[AdoraV2Tool._utils] account_name '{account_name}' sanitizes to empty string"
            )
            return None, None

        return (
            get_client_secret_with_fallback(f"{name}_ADORA_API_KEY"),
            get_client_secret_with_fallback(f"{name}_ADORA_API_SECRET"),
        )
    except Exception as e:
        logger.error(f"[AdoraV2Tool._utils] Error: {e}")
        return None, None
