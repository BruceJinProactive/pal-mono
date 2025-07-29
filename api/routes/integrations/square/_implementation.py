import binascii
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests
from fastapi import Request, status
from fastapi.responses import JSONResponse, RedirectResponse

import db
from db.repositories.account_repository import AccountRepository
from db.repositories.integration_repository import IntegrationRepository
from db.tables.types import AuthType, IntegrationProvider, IntegrationType
from services.integration_service import create_integration
from services.integration_service.schema import (
    CreateIntegrationParams,
    IntegrationCredentials,
)
from services.service_utils import get_server_url
from utils.log import logger
from utils.secret import get_client_secret

from ._util import get_square_client_id, get_square_client_secret, refresh_square_token
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
    expires_at = token_data.get("expires_at")

    if not access_token or not refresh_token or not merchant_id or not expires_at:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Missing access token, refresh token, merchant ID, or expires_at in response"
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

        # Parse expires_at if provided
        parsed_expires_at = None
        if expires_at:
            parsed_expires_at = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )
        parsed_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        integration_params = CreateIntegrationParams(
            provider=IntegrationProvider.square,
            integration_type=IntegrationType.pos,
            auth_type=AuthType.oauth,
            business_id=merchant_id,
            credentials=IntegrationCredentials(
                access_token=access_token,
                refresh_token=refresh_token,
            ),
            expires_at=parsed_expires_at,
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
        session.rollback()
        logger.error(f"Error creating Square integration: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Failed to create integration: {str(e)}"},
        )
    finally:
        session.close()


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
    expiration_threshold = datetime.now(timezone.utc) + timedelta(days=days_threshold)

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

            # Use the refresh_square_token function
            result = refresh_square_token(account.name, integration.id, session)
            if result["success"]:
                logger.info(
                    f"Successfully refreshed token for integration {integration.id}"
                )
                total_refreshed += 1
            else:
                logger.error(
                    f"Failed to refresh token for integration {integration.id}: {result['error']}"
                )
                errors.append(
                    f"Failed to refresh token for integration {integration.id}: {result['error']}"
                )
                total_failed += 1

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


def transform_square_location_to_store_location(
    square_location: dict, integration_id: str
) -> dict:
    """
    Transform Square location data to match manage-app's StoreLocation interface.

    Args:
        square_location: Raw location data from Square API
        integration_id: The integration ID to include in the response

    Returns:
        dict: Transformed location data matching StoreLocation interface
    """
    address = square_location.get("address", {})

    address_parts = []
    if address.get("address_line_1"):
        address_parts.append(address["address_line_1"])
    if address.get("address_line_2"):
        address_parts.append(address["address_line_2"])

    return {
        "id": square_location.get("id", ""),
        "name": square_location.get("name", ""),
        "address": ", ".join(address_parts) if address_parts else "",
        "city": address.get("locality", ""),
        "state": address.get("administrative_district_level_1", ""),
        "zip_code": address.get("postal_code", ""),
        "phone_number": square_location.get("phone_number"),
        "store_id": square_location.get("id", ""),
        "integration_id": str(integration_id),
        "created_at": square_location.get("created_at", ""),
        "updated_at": square_location.get("updated_at"),
    }


def get_merchant_locations(
    session, account_name: str, integration_id: uuid.UUID
) -> dict:
    """
    Get all locations for a Square merchant.

    Args:
        session: Database session
        account_name: Name of the account
        integration_id: UUID of the Square integration

    Returns:
        dict: Response with locations data or error message
    """
    try:
        # Get account
        account_repository = AccountRepository(session)
        account = account_repository.get_account(account_name)
        if not account:
            return {"success": False, "error": f"Account {account_name} not found"}

        # Get integration
        integration_repository = IntegrationRepository(session)
        integration = integration_repository.get_integration_by_id(
            account.id, integration_id
        )
        if not integration:
            return {
                "success": False,
                "error": f"Integration {integration_id} not found for account {account_name}",
            }

        # Verify it's a Square integration
        if integration.provider != IntegrationProvider.square:
            return {
                "success": False,
                "error": f"Integration {integration_id} is not a Square integration",
            }

        # Get access token from secret manager
        if not integration.secret_key:
            return {
                "success": False,
                "error": f"Integration {integration_id} does not have a secret_key",
            }

        secrets_json = get_client_secret(integration.secret_key)
        secrets = json.loads(secrets_json)
        access_token = secrets.get("access_token")
        if not access_token:
            return {
                "success": False,
                "error": f"No access token found in secret manager for integration {integration_id}",
            }

        # Call Square Locations API
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Square-Version": "2025-05-21",
            "Content-Type": "application/json",
        }

        # Determine if we should use production or sandbox
        use_production = True  # You might want to make this configurable
        base_url = (
            "connect.squareup.com" if use_production else "connect.squareupsandbox.com"
        )

        response = requests.get(f"https://{base_url}/v2/locations", headers=headers)

        if response.status_code != 200:
            logger.error(f"Failed to get Square locations: {response.text}")
            return {
                "success": False,
                "error": f"Failed to get Square locations: {response.text}",
            }

        locations_data = response.json()

        raw_locations = locations_data.get("locations", [])
        transformed_locations = [
            transform_square_location_to_store_location(location, str(integration_id))
            for location in raw_locations
        ]

        return {
            "success": True,
            "locations": transformed_locations,
            "total_locations": len(transformed_locations),
        }

    except Exception as e:
        logger.error(f"Error getting Square locations for account {account_name}: {e}")
        return {"success": False, "error": f"Error getting Square locations: {str(e)}"}
