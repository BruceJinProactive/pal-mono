import logging
from dataclasses import dataclass
from typing import Optional

from db.tables.pos_integration import POSProvider

# Import POS token exchange functions from each tool
from tools.adora_tool._apis import get_adora_pos_auth_token
from tools.opentable_tool._apis import get_opentable_access_token
from tools.toast_tool._apis import get_toast_access_token

# from tools.yelp_tool._apis import get_yelp_access_token  # Not implemented
# For Olo and Square, the 'token' is just the API key, not an exchange
from utils.secret import get_client_secret_with_fallback, upsert_client_secret

logger = logging.getLogger(__name__)


@dataclass
class TokenExchangeConfig:
    """Configuration for POS token exchange operations."""

    qa_store: bool = False
    token_api_endpoint: Optional[str] = None
    use_production: bool = False


def _get_adora_token(
    client_key: str, client_secret: str, config: TokenExchangeConfig
) -> Optional[str]:
    """Get access token for Adora provider."""
    token_obj = get_adora_pos_auth_token(
        key=client_key,
        secret=client_secret,
        qa_store=config.qa_store,
        token_api_endpoint=config.token_api_endpoint,
    )
    return (
        token_obj.access_token
        if token_obj and hasattr(token_obj, "access_token")
        else None
    )


def _get_toast_token(client_key: str, client_secret: str) -> Optional[str]:
    """Get access token for Toast provider."""
    token_obj = get_toast_access_token(client_key, client_secret)
    return (
        token_obj.access_token
        if token_obj and hasattr(token_obj, "access_token")
        else None
    )


def _get_olo_token(client_key: str) -> str:
    """Get access token for Olo provider (API key is the token)."""
    return client_key


def _get_square_token(client_key: str) -> str:
    """Get access token for Square provider (API key is the token)."""
    return client_key


def _get_yelp_token() -> Optional[str]:
    """Get access token for Yelp provider (not implemented)."""
    logger.warning("Yelp access token exchange not implemented.")
    return None


def _get_opentable_token(
    client_key: str, client_secret: str, config: TokenExchangeConfig
) -> Optional[str]:
    """Get access token for OpenTable provider."""
    token_obj = get_opentable_access_token(
        client_key, client_secret, use_production=config.use_production
    )
    return (
        token_obj.access_token
        if token_obj and hasattr(token_obj, "access_token")
        else None
    )


def store_pos_credentials(
    provider: POSProvider,
    project_name: str,
    client_key: str,
    client_secret: str,
) -> None:
    """
    Store the client_key and client_secret for a POS provider in the secret manager.
    """
    key_key = f"{project_name.upper()}_{provider.value.upper()}_CLIENT_KEY"
    secret_key = f"{project_name.upper()}_{provider.value.upper()}_CLIENT_SECRET"
    upsert_client_secret(key_key, client_key)
    upsert_client_secret(secret_key, client_secret)
    logger.info(f"Successfully stored credentials for {provider.value} provider")


def get_pos_access_token(
    provider: POSProvider,
    project_name: str,
    store_identifier: str,
    config: Optional[TokenExchangeConfig] = None,
) -> Optional[str]:
    """
    Retrieve the client_key and client_secret from the secret manager and exchange them for an access token.
    Returns the access token if successful, else None. Does not store the access token.

    Args:
        provider: The POS provider to get the access token for
        project_name: The name of the project
        store_identifier: The store identifier
        config: Optional configuration for token exchange (defaults to TokenExchangeConfig())
    """
    if config is None:
        config = TokenExchangeConfig()

    key_key = f"{project_name.upper()}_{provider.value.upper()}_CLIENT_KEY"
    secret_key = f"{project_name.upper()}_{provider.value.upper()}_CLIENT_SECRET"

    try:
        client_key = get_client_secret_with_fallback(key_key)
        client_secret = get_client_secret_with_fallback(secret_key)
    except Exception as e:
        logger.error(f"Could not retrieve credentials for {provider.value}: {e}")
        return None

    try:
        # Provider-specific token retrieval
        if provider == POSProvider.ADORA:
            access_token = _get_adora_token(client_key, client_secret, config)
        elif provider == POSProvider.TOAST:
            access_token = _get_toast_token(client_key, client_secret)
        elif provider == POSProvider.OLO:
            access_token = _get_olo_token(client_key)
        elif provider == POSProvider.SQUARE:
            access_token = _get_square_token(client_key)
        elif provider == POSProvider.YELP:
            access_token = _get_yelp_token()
        elif provider == POSProvider.OPENTABLE:
            access_token = _get_opentable_token(client_key, client_secret, config)
        else:
            logger.warning(f"Provider {provider} not supported for token exchange.")
            return None

        if access_token:
            logger.debug(f"Retrieved access token for {provider.value} (not stored)")
            return access_token

        logger.error(f"Failed to obtain access token for {provider.value}")
        return None

    except Exception as e:
        logger.exception(f"Error retrieving access token for {provider.value}: {e}")
        return None
