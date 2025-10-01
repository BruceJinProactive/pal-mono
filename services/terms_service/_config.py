import os
from typing import Optional

DOCUSIGN_INTEGRATION_KEY = os.getenv("DOCUSIGN_INTEGRATION_KEY")
DOCUSIGN_USER_ID = os.getenv("DOCUSIGN_USER_ID")
DOCUSIGN_ACCOUNT_ID = os.getenv("DOCUSIGN_ACCOUNT_ID")
DOCUSIGN_PRIVATE_KEY = os.getenv("DOCUSIGN_PRIVATE_KEY")

DOCUSIGN_BASE_PATH = os.getenv(
    "DOCUSIGN_BASE_PATH", "https://demo.docusign.net/restapi"
)
DOCUSIGN_OAUTH_HOST = os.getenv("DOCUSIGN_OAUTH_HOST", "account-d.docusign.com")

DOCUSIGN_FRAME_ANCESTOR_DEV = "https://apps-d.docusign.com"
DOCUSIGN_FRAME_ANCESTOR_PROD = "https://apps.docusign.com"
DOCUSIGN_MESSAGE_ORIGIN_DEV = "https://apps-d.docusign.com"
DOCUSIGN_MESSAGE_ORIGIN_PROD = "https://apps.docusign.com"

IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"
DOCUSIGN_FRAME_ANCESTOR = (
    DOCUSIGN_FRAME_ANCESTOR_PROD if IS_PRODUCTION else DOCUSIGN_FRAME_ANCESTOR_DEV
)
DOCUSIGN_MESSAGE_ORIGIN = (
    DOCUSIGN_MESSAGE_ORIGIN_PROD if IS_PRODUCTION else DOCUSIGN_MESSAGE_ORIGIN_DEV
)


def get_docusign_config() -> dict:
    """Get DocuSign configuration."""
    return {
        "integration_key": DOCUSIGN_INTEGRATION_KEY,
        "user_id": DOCUSIGN_USER_ID,
        "account_id": DOCUSIGN_ACCOUNT_ID,
        "private_key": DOCUSIGN_PRIVATE_KEY,
        "base_path": DOCUSIGN_BASE_PATH,
        "oauth_host": DOCUSIGN_OAUTH_HOST,
        "frame_ancestor": DOCUSIGN_FRAME_ANCESTOR,
        "message_origin": DOCUSIGN_MESSAGE_ORIGIN,
        "is_production": IS_PRODUCTION,
    }


def validate_config() -> tuple[bool, Optional[str]]:
    """
    Validate that all required configuration is present.

    Returns:
        tuple: (is_valid, error_message)
    """
    required_vars = {
        "DOCUSIGN_INTEGRATION_KEY": DOCUSIGN_INTEGRATION_KEY,
        "DOCUSIGN_USER_ID": DOCUSIGN_USER_ID,
        "DOCUSIGN_ACCOUNT_ID": DOCUSIGN_ACCOUNT_ID,
        "DOCUSIGN_PRIVATE_KEY": DOCUSIGN_PRIVATE_KEY,
    }

    missing = [key for key, value in required_vars.items() if not value]

    if missing:
        return False, f"Missing required environment variables: {', '.join(missing)}"

    return True, None
