import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from fastapi import HTTPException, status

from api.schemas.admin.integration import IntegrationRequest
from db.tables.types import IntegrationProvider

# Import POS token exchange functions from each tool
from tools.adora_tool._apis import get_adora_pos_auth_token
from tools.opentable_tool._apis import get_opentable_access_token
from tools.toast_tool._apis import get_toast_access_token
from utils.secret import upsert_client_secret

# from tools.yelp_tool._apis import get_yelp_access_token  # Not implemented
# For Olo and Square, the 'token' is just the API key, not an exchange


logger = logging.getLogger(__name__)


@dataclass
class TokenExchangeConfig:
    """Configuration for POS token exchange operations."""

    qa_store: bool = False
    token_api_endpoint: Optional[str] = None
    use_production: bool = False


def _get_adora_token(
    client_id: str, client_secret: str, config: TokenExchangeConfig
) -> Optional[str]:
    """Get access token for Adora provider."""
    token_obj = get_adora_pos_auth_token(
        key=client_id,
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


def _get_square_token(merchant_id: str) -> Optional[str]:
    """Get access token for Square provider using Integration table (merchant_id required)."""
    import db
    from db import IntegrationRepository
    from db.tables.types import IntegrationProvider

    if not merchant_id:
        logger.error("merchant_id is required for Square OAuth token retrieval.")
        return None

    try:
        session = next(db.get_db())
        try:
            integration_repository = IntegrationRepository(session)
            integrations = (
                integration_repository.get_integrations_by_provider_and_business_id(
                    IntegrationProvider.square, merchant_id
                )
            )

            if not integrations:
                logger.error(
                    f"No Square integration found for merchant_id {merchant_id}"
                )
                return None

            integration = max(integrations, key=lambda x: x.created_at)
            return integration.access_token
        finally:
            session.close()

    except Exception as e:
        logger.error(
            f"Failed to retrieve Square access token for merchant_id {merchant_id}: {e}"
        )
        return None


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


def get_pos_access_token(
    provider: IntegrationProvider,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    config: Optional[TokenExchangeConfig] = None,
    business_id: Optional[str] = None,
) -> Optional[str]:
    """
    Retrieve the client_key and client_secret from the secret manager and exchange them for an access token.
    Returns the access token if successful, else None. Does not store the access token.

    Args:
        provider: The POS provider to get the access token for
        business_id: The Square merchant_id (required for Square)
        project_name: The name of the project
        store_identifier: The store identifier
        config: Optional configuration for token exchange (defaults to TokenExchangeConfig())
    """
    if config is None:
        config = TokenExchangeConfig()

    try:
        # Provider-specific token retrieval
        if provider == IntegrationProvider.adora:
            if not client_id or not client_secret:
                raise ValueError(
                    "Client ID and client secret are required for Adora provider"
                )
            access_token = _get_adora_token(client_id, client_secret, config)
        elif provider == IntegrationProvider.toast:
            if not client_id or not client_secret:
                raise ValueError(
                    "Client ID and client secret are required for Toast provider"
                )
            access_token = _get_toast_token(client_id, client_secret)
        elif provider == IntegrationProvider.olo:
            if not client_id:
                raise ValueError("Client ID is required for Olo provider")
            access_token = _get_olo_token(client_id)
        elif provider == IntegrationProvider.square:
            if not business_id:
                raise ValueError(
                    "business_id (merchant_id) is required for Square provider"
                )
            access_token = _get_square_token(business_id)
        elif provider == IntegrationProvider.yelp:
            access_token = _get_yelp_token()
        elif provider == IntegrationProvider.opentable:
            if not client_id or not client_secret:
                raise ValueError(
                    "Client ID and client secret are required for OpenTable provider"
                )
            access_token = _get_opentable_token(client_id, client_secret, config)
        else:
            logger.warning(f"Provider {provider} not supported for token exchange.")
            return None

        if access_token:
            logger.debug(f"Retrieved access token for {provider} (not stored)")
            return access_token

        logger.error(f"Failed to obtain access token for {provider}")
        return None

    except Exception as e:
        logger.exception(f"Error retrieving access token for {provider}: {e}")
        return None


def _store_integration_credentials(
    provider: IntegrationProvider,
    account_name: str,
    client_id: str,
    client_secret: str,
) -> Tuple[str, str]:
    """
    Store the client_key and client_secret for a POS provider in the secret manager.
    """
    id_key = f"{account_name.upper()}_{provider.value.upper()}_CLIENT_ID"
    secret_key = f"{account_name.upper()}_{provider.value.upper()}_CLIENT_SECRET"
    upsert_client_secret(id_key, client_id)
    upsert_client_secret(secret_key, client_secret)
    logger.info(f"Successfully stored credentials for {provider.value} provider")
    return id_key, secret_key


def store_integration_credentials(
    integration: IntegrationRequest,
    account_name: str,
) -> IntegrationRequest:
    """
    Store the client_key and client_secret for a POS provider in the secret manager.
    """
    # Validate credentials based on provider requirements

    if integration.provider in [
        IntegrationProvider.adora,
        IntegrationProvider.toast,
        IntegrationProvider.opentable,
    ]:
        if not (integration.client_id and integration.client_secret):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client ID and Client Secret are required for this provider",
            )
    elif integration.provider in [IntegrationProvider.olo, IntegrationProvider.square]:
        if not integration.client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client ID is required for this provider",
            )

    if integration.client_id:
        id_key, secret_key = _store_integration_credentials(
            integration.provider,
            account_name,
            integration.client_id,
            integration.client_secret or "",
        )
        integration.client_id = id_key
        integration.client_secret = secret_key
    return integration
