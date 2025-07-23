import binascii
import json
import os
from datetime import datetime, timedelta

import requests
from fastapi import Request, status
from fastapi.responses import JSONResponse, RedirectResponse

import db
from db.repositories.account_repository import AccountRepository
from db.repositories.integration_repository import IntegrationRepository
from db.tables.types import AuthType, IntegrationProvider, IntegrationType
from services.integration_service import create_integration
from services.integration_service._utils import update_integration_credentials
from services.integration_service.schema import (
    CreateIntegrationParams,
    IntegrationCredentials,
)
from services.service_utils import get_server_url
from utils.log import logger
from utils.secret import get_client_secret

from ._util import get_square_client_id, get_square_client_secret
from ._valid import _oauth_state, valid_request

SQUARE_AUTH_URL = "https://connect.squareup.com/oauth2/authorize"
SQUARE_TOKEN_URL = "https://connect.squareup.com/oauth2/token"
SQUARE_SCOPES = ["ITEMS_READ", "ORDERS_READ", "ORDERS_WRITE", "MERCHANT_PROFILE_READ"]


async def install(request: Request):
    account_name = request.query_params.get("account_name")
    if not account_name:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "account_name parameter is required"},
        )

    # Generate state for CSRF protection and store account context
    state = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
    _oauth_state[state] = account_name

    client_id = get_square_client_id()
    scopes = " ".join(SQUARE_SCOPES)
    # Build the redirect URI dynamically
    redirect_uri = f"{get_server_url()}/v1/integrations/square/callback"
    auth_url = (
        f"{SQUARE_AUTH_URL}?client_id={client_id}"
        f"&scope={scopes}"
        f"&session=False"
        f"&state={state}"
        f"&redirect_uri={redirect_uri}"
    )
    return RedirectResponse(auth_url)


async def callback(request: Request):
    # Validate state parameter for CSRF protection and get account_name
    account_name_result = valid_request(request, is_callback=True)
    if not isinstance(account_name_result, str):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid state validation"},
        )
    account_name = account_name_result

    code = request.query_params.get("code")

    if not code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing authorization code"},
        )

    try:
        client_id = get_square_client_id()
        client_secret = get_square_client_secret()
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(e)},
        )

    # Always build the redirect_uri dynamically for token exchange
    redirect_uri = f"{get_server_url()}/v1/integrations/square/callback"

    # Exchange code for access token
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(SQUARE_TOKEN_URL, json=data, headers=headers)
    if resp.status_code != 200:
        print(f"[DEBUG] Token exchange failed: {resp.text}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Failed to exchange code for token",
                "details": resp.text,
            },
        )
    token_data = resp.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    merchant_id = token_data.get("merchant_id")

    if not access_token or not refresh_token or not merchant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Missing access token, refresh token, or merchant ID in response"
            },
        )

    session = next(db.get_db())
    try:
        account_repository = db.AccountRepository(session)
        account = account_repository.get_account(account_name)
        if not account:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Account {account_name} not found"},
            )

        integration_params = CreateIntegrationParams(
            provider=IntegrationProvider.square,
            integration_type=IntegrationType.pos,
            auth_type=AuthType.oauth,
            business_id=merchant_id,
            credentials=IntegrationCredentials(
                access_token=access_token,
                refresh_token=refresh_token,
            ),
        )

        created_integration = create_integration(
            session=session,
            account=account,
            params=integration_params,
        )

        return JSONResponse(
            {
                "message": "Integration created successfully!",
                "merchant_id": merchant_id,
                "integration_id": str(created_integration.id),
            }
        )
    except Exception as e:
        logger.error(f"[DEBUG] Failed to create integration: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Failed to create integration: {e}"},
        )
    finally:
        session.close()


async def refresh(request: Request):
    """
    FastAPI endpoint to refresh the Square access token for the given account.
    Expects a JSON body with 'account_name'.
    """
    try:
        data = await request.json()
        account_name = data.get("account_name")
        if not account_name:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Missing 'account_name' in request body"},
            )

        SQUARE_TOKEN_URL = "https://connect.squareup.com/oauth2/token"
        client_id = get_square_client_id()
        client_secret = get_square_client_secret()
        session = next(db.get_db())
        try:
            account_repository = AccountRepository(session)
            account = account_repository.get_account(account_name)
            if not account:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": f"Account {account_name} not found"},
                )
            integration_repository = IntegrationRepository(session)
            integrations = integration_repository.get_integrations_by_provider_and_type(
                account.id, IntegrationProvider.square, IntegrationType.pos
            )
            if not integrations:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": f"No Square integration found for account '{account_name}'"
                    },
                )
            integration = integrations[0]
            if not integration.secret_key:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": f"Integration for account '{account_name}' does not have a secret_key"
                    },
                )
            secrets_json = get_client_secret(integration.secret_key)
            secrets = json.loads(secrets_json)
            refresh_token = secrets.get("refresh_token")
            if not refresh_token:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": f"No refresh token found in secret manager for account '{account_name}'"
                    },
                )
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
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"error": f"Failed to refresh Square token: {resp.text}"},
                )
            token_data = resp.json()
            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token")
            if not new_access_token or not new_refresh_token:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={
                        "error": "Missing access token or refresh token in Square response"
                    },
                )
            creds = IntegrationCredentials(
                access_token=new_access_token, refresh_token=new_refresh_token
            )
            update_integration_credentials(account, creds, integration)
            session.commit()
            logger.info(
                f"Successfully refreshed Square token for account '{account_name}'"
            )
            return JSONResponse({"status": "success"})
        except Exception as e:
            session.rollback()
            logger.error(
                f"Error refreshing Square token for account '{account_name}': {e}"
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": str(e)},
            )
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error in refresh endpoint: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": str(e)},
        )


# TODO: Implement api_chat and api_project_info if needed for Square, similar to Shopify


def check_and_refresh_expiring_square_tokens(session, days_threshold: int = 7) -> dict:
    """
    Check all Square integrations and refresh tokens that are expiring within the specified days.

    Args:
        session: Database session
        days_threshold: Number of days before expiration to trigger refresh (default: 7)

    Returns:
        dict: Summary of the operation including counts of checked, refreshed, and failed integrations
    """
    integration_repository = IntegrationRepository(session)
    account_repository = AccountRepository(session)

    # Get all Square integrations
    square_integrations = (
        integration_repository.get_all_integrations_by_provider_and_type(
            provider=IntegrationProvider.square, integration_type=IntegrationType.pos
        )
    )

    if not square_integrations:
        logger.info("No Square integrations found")
        return {
            "total_checked": 0,
            "total_refreshed": 0,
            "total_failed": 0,
            "errors": [],
        }

    logger.info(f"Found {len(square_integrations)} Square integrations to check")

    total_refreshed = 0
    total_failed = 0
    errors = []

    # Calculate the expiration threshold
    expiration_threshold = datetime.now() + timedelta(days=days_threshold)

    for integration in square_integrations:
        try:
            # Skip integrations without secret_key or expires_at
            if not integration.secret_key:
                logger.warning(
                    f"Integration {integration.id} has no secret_key, skipping"
                )
                continue

            # Check if expires_at column exists and has a value
            if not hasattr(integration, "expires_at") or integration.expires_at is None:
                logger.warning(
                    f"Integration {integration.id} has no expires_at value, skipping"
                )
                continue

            # Check if token expires within the threshold
            if integration.expires_at > expiration_threshold:
                logger.debug(
                    f"Integration {integration.id} expires at {integration.expires_at}, not within threshold"
                )
                continue

            logger.info(
                f"Integration {integration.id} expires at {integration.expires_at}, refreshing token"
            )

            # Get account for this integration
            account = account_repository.get_account_by_id(integration.account_id)
            if not account:
                logger.error(
                    f"Account {integration.account_id} not found for integration {integration.id}"
                )
                errors.append(
                    f"Account {integration.account_id} not found for integration {integration.id}"
                )
                total_failed += 1
                continue

            # Get secrets from secret manager
            secrets_json = get_client_secret(integration.secret_key)
            secrets = json.loads(secrets_json)
            refresh_token = secrets.get("refresh_token")

            if not refresh_token:
                logger.error(f"No refresh token found for integration {integration.id}")
                errors.append(
                    f"No refresh token found for integration {integration.id}"
                )
                total_failed += 1
                continue

            # Call Square API to refresh token
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
                logger.error(
                    f"Failed to refresh Square token for integration {integration.id}: {resp.text}"
                )
                errors.append(
                    f"Failed to refresh Square token for integration {integration.id}: {resp.text}"
                )
                total_failed += 1
                continue

            token_data = resp.json()
            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token")

            if not new_access_token or not new_refresh_token:
                logger.error(
                    f"Missing access token or refresh token in Square response for integration {integration.id}"
                )
                errors.append(
                    f"Missing access token or refresh token in Square response for integration {integration.id}"
                )
                total_failed += 1
                continue

            # Update integration credentials
            creds = IntegrationCredentials(
                access_token=new_access_token, refresh_token=new_refresh_token
            )
            update_integration_credentials(account, creds, integration)

            # Update expires_at if provided in response
            if "expires_at" in token_data:
                integration.expires_at = datetime.fromisoformat(
                    token_data["expires_at"].replace("Z", "+00:00")
                )

            session.commit()
            logger.info(
                f"Successfully refreshed token for integration {integration.id}"
            )
            total_refreshed += 1

        except Exception as e:
            logger.error(
                f"Error refreshing token for integration {integration.id}: {e}"
            )
            errors.append(
                f"Error refreshing token for integration {integration.id}: {str(e)}"
            )
            total_failed += 1
            session.rollback()

    result = {
        "total_checked": len(square_integrations),
        "total_refreshed": total_refreshed,
        "total_failed": total_failed,
        "errors": errors,
    }

    logger.info(f"Token refresh summary: {result}")
    return result
