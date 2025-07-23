import json
import os
from datetime import datetime

import requests

import db
from db.repositories.account_repository import AccountRepository
from db.repositories.integration_repository import IntegrationRepository
from db.tables.types import IntegrationProvider, IntegrationType
from services.integration_service._utils import update_integration_credentials
from services.integration_service.schema import IntegrationCredentials
from utils import secret
from utils.log import logger
from utils.secret import get_client_secret


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


def refresh_square_token(account_name: str, session=None) -> dict:
    """
    Refreshes the Square access token for the given account.

    Args:
        account_name: Name of the account to refresh token for
        session: Database session (optional, will create new one if not provided)

    Returns:
        dict: Result with 'success' boolean and optional 'error' message
    """
    close_session = False
    if session is None:
        session = next(db.get_db())
        close_session = True

    try:
        account_repository = AccountRepository(session)
        account = account_repository.get_account(account_name)
        if not account:
            return {"success": False, "error": f"Account {account_name} not found"}

        integration_repository = IntegrationRepository(session)
        integrations = integration_repository.get_integrations_by_provider_and_type(
            account.id, IntegrationProvider.square, IntegrationType.pos
        )
        if not integrations:
            return {
                "success": False,
                "error": f"No Square integration found for account '{account_name}'",
            }

        integration = integrations[0]
        if not integration.secret_key:
            return {
                "success": False,
                "error": f"Integration for account '{account_name}' does not have a secret_key",
            }

        secrets_json = get_client_secret(integration.secret_key)
        secrets = json.loads(secrets_json)
        refresh_token = secrets.get("refresh_token")
        if not refresh_token:
            return {
                "success": False,
                "error": f"No refresh token found in secret manager for account '{account_name}'",
            }

        SQUARE_TOKEN_URL = "https://connect.squareup.com/oauth2/token"
        client_id = get_square_client_id()
        client_secret = get_square_client_secret()

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/json"}
        resp = requests.post(SQUARE_TOKEN_URL, json=data, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to refresh Square token: {resp.text}")
            return {
                "success": False,
                "error": f"Failed to refresh Square token: {resp.text}",
            }

        token_data = resp.json()
        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get("refresh_token")
        if not new_access_token or not new_refresh_token:
            return {
                "success": False,
                "error": "Missing access token or refresh token in Square response",
            }

        # Update integration credentials
        creds = IntegrationCredentials(
            access_token=new_access_token, refresh_token=new_refresh_token
        )
        update_integration_credentials(account, creds, integration)

        # Update expires_at field if expires_at is provided in the response
        expires_at = token_data.get("expires_at")
        if expires_at:
            # Parse the expires_at timestamp from Square API
            integration.expires_at = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )
            logger.info(
                f"Updated expires_at to {integration.expires_at} for account '{account_name}'"
            )

        session.commit()
        logger.info(f"Successfully refreshed Square token for account '{account_name}'")
        return {"success": True}

    except Exception as e:
        session.rollback()
        logger.error(f"Error refreshing Square token for account '{account_name}': {e}")
        return {"success": False, "error": str(e)}
    finally:
        if close_session:
            session.close()
