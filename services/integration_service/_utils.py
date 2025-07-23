import json
import random
import string

import db
from db import Account
from db.tables.integration import Integration
from db.tables.types import AuthType
from services.integration_service.schema import (
    IntegrationCredentials,
    IntegrationDetail,
)
from utils.log import logger
from utils.secret import get_client_secret, upsert_client_secret


def _generate_secret_key(
    account_name: str, integration_type: str, provider_name: str, auth_type: str
) -> str:
    """
    Generate a unique secret key for storing integration credentials.

    Format: {account_name}_{integration_type}_{provider_name}_{auth_type}_{random_suffix}
    """
    # Clean account name (remove non-alphanumeric characters and convert to uppercase)
    clean_account_name = "".join(c for c in account_name if c.isalnum()).upper()

    # Generate 4 random characters (mix of letters and numbers)
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))

    # Build the key with integration ID for uniqueness
    secret_key = f"{clean_account_name}_{integration_type.upper()}_{provider_name.upper()}_{auth_type.upper()}_{random_suffix}"

    return secret_key


def _extract_auth_secrets(
    credentials: IntegrationCredentials, auth_type: AuthType
) -> dict:
    """
    Extract authentication secrets based on auth_type and return as a dictionary.
    Only includes non-None/non-empty fields to support partial updates.
    """
    secrets = {}

    if auth_type == AuthType.oauth:
        if credentials.access_token:
            secrets["access_token"] = credentials.access_token
        if credentials.refresh_token:
            secrets["refresh_token"] = credentials.refresh_token

    elif auth_type == AuthType.api_key:
        if credentials.api_key:
            secrets["api_key"] = credentials.api_key

    elif auth_type == AuthType.client_secret:
        if credentials.client_id:
            secrets["client_id"] = credentials.client_id
        if credentials.client_secret:
            secrets["client_secret"] = credentials.client_secret

    else:
        raise ValueError(f"Unsupported authentication type: {auth_type}")

    if not secrets:
        raise ValueError(f"No valid credentials provided for {auth_type}")

    return secrets


def _get_integration_credentials(secret_key: str) -> dict:
    try:
        secrets_json = get_client_secret(secret_key)
        return json.loads(secrets_json)
    except KeyError:
        logger.error(f"Secret key '{secret_key}' not found in secret manager")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format for secret key '{secret_key}': {e}")
        raise


def update_integration_credentials(
    account: Account,
    credentials: IntegrationCredentials,
    integration: db.Integration,
):
    # Extract authentication secrets based on auth_type (partial updates supported)
    new_auth_secrets = _extract_auth_secrets(credentials, integration.auth_type)

    # Generate secret key if not provided
    secret_key = integration.secret_key
    if not secret_key:
        secret_key = _generate_secret_key(
            account_name=account.name,
            integration_type=integration.integration_type.value,
            provider_name=integration.provider.value,
            auth_type=integration.auth_type.value,
        )
        # For new integrations, store the provided credentials
        final_auth_secrets = new_auth_secrets
    else:
        # For existing integrations, merge new credentials with existing ones
        try:
            existing_auth_secrets = _get_integration_credentials(secret_key)
            # Merge existing secrets with new ones (new ones take precedence)
            final_auth_secrets = {**existing_auth_secrets, **new_auth_secrets}
        except (KeyError, json.JSONDecodeError):
            # If we can't retrieve existing secrets, just use the new ones
            logger.warning(
                f"Could not retrieve existing secrets for key {secret_key}, using new credentials only"
            )
            final_auth_secrets = new_auth_secrets

    # Store merged secrets in secret manager
    secrets_json = json.dumps(final_auth_secrets)
    upsert_client_secret(secret_key, secrets_json)

    logger.info(
        f"Updated integration secrets for account {account.name} with key {secret_key}"
    )
    return secret_key


def build_integration_detail(integration: Integration):
    credentials = {}
    if integration.secret_key:
        credentials = _get_integration_credentials(integration.secret_key)

    return IntegrationDetail(
        id=integration.id,
        account_id=integration.account_id,
        integration_type=integration.integration_type,
        provider=integration.provider,
        auth_type=integration.auth_type,
        business_id=integration.business_id,
        raw_config=integration.raw_config,
        access_token=credentials.get("access_token"),
        refresh_token=credentials.get("refresh_token"),
        client_id=credentials.get("client_id"),
        client_secret=credentials.get("client_secret"),
        api_key=credentials.get("api_key"),
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        expires_at=integration.expires_at,
    )
