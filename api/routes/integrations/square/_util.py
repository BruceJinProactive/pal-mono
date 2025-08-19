import asyncio
import json
import os
import uuid
from datetime import datetime

import requests

import db
from db.repositories.account_repository import AccountRepository
from db.repositories.integration_repository import IntegrationRepository
from db.tables.types import IntegrationProvider
from services.integration_service._utils import update_integration_credentials
from services.integration_service.schema import IntegrationCredentials
from services.transaction_service import update_transaction_by_order_number_helper
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


def refresh_square_token(
    account_name: str, integration_id: uuid.UUID, session=None
) -> dict:
    """
    Refreshes the Square access token for the given account.

    Args:
        account_name: Name of the account to refresh token for
        integration_id: ID of the integration to refresh token for
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
        integration = integration_repository.get_integration_by_id(
            account.id, integration_id
        )
        if not integration:
            return {
                "success": False,
                "error": f"No Square integration found for account '{account_name}' with id '{integration_id}'",
            }
        if not integration.secret_key:
            return {
                "success": False,
                "error": f"Integration for account '{account_name}' with id '{integration_id}' does not have a secret_key",
            }

        secrets_json = get_client_secret(integration.secret_key)
        secrets = json.loads(secrets_json)
        refresh_token = secrets.get("refresh_token")
        if not refresh_token:
            return {
                "success": False,
                "error": f"No refresh token found in secret manager for account '{account_name}' with id '{integration_id}'",
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
                f"Updated expires_at to {integration.expires_at} for account '{account_name}' with id '{integration_id}'"
            )

        session.commit()
        logger.info(
            f"Successfully refreshed Square token for account '{account_name}' with id '{integration_id}'"
        )
        return {"success": True}

    except Exception as e:
        session.rollback()
        logger.error(
            f"Error refreshing Square token for account '{account_name}' with id '{integration_id}': {e}"
        )
        return {"success": False, "error": str(e)}
    finally:
        if close_session:
            session.close()


async def handle_payment_updated(webhook_request) -> None:
    """
    Handle payment.updated webhook events.

    Updates existing transaction status using update_transaction_by_order_number.

    Args:
        webhook_request: The Square webhook request containing payment data
    """
    try:
        payment_data = (
            webhook_request.get("data", {}).get("object", {}).get("payment", {})
        )

        # Extract required fields
        payment_id = payment_data.get("id")
        order_id = payment_data.get("order_id")
        location_id = payment_data.get("location_id")
        payment_created_at = payment_data.get("created_at")
        receipt_url = payment_data.get("receipt_url")
        payment_status = payment_data.get("status")

        # Extract total money amount
        total_money = payment_data.get("total_money", {})
        total_amount = (
            total_money.get("amount", 0) / 100
        )  # Convert from cents to dollars

        logger.info(
            "[Square Webhook] Processing payment.updated event",
            extra={
                "payment_id": payment_id,
                "order_id": order_id,
                "location_id": location_id,
                "payment_created_at": payment_created_at,
                "receipt_url": receipt_url,
                "payment_status": payment_status,
                "total_amount": total_amount,
            },
        )

        # Update transaction in database if order_id exists
        if order_id and location_id:
            # Map Square payment status to our transaction status
            if payment_status == "COMPLETED":
                transaction_status = "paid"
            else:
                # Default to pending for other statuses or if payment_status is None
                transaction_status = "pending"

            # Update transaction using transaction helper
            success = await asyncio.to_thread(
                update_transaction_by_order_number_helper,
                external_transaction_number=order_id,
                store_id=location_id,
                vendor=IntegrationProvider.square,
                status=transaction_status,
                tracking_link=receipt_url,
                session=None,  # Let helper create its own sync session
            )

            if success:
                logger.info(
                    f"[Square Webhook] Successfully updated transaction for order {order_id}"
                )
            else:
                logger.warning(
                    f"[Square Webhook] Failed to update transaction for order {order_id} - transaction not found"
                )
        else:
            logger.warning(
                "[Square Webhook] Missing order_id or location_id - cannot update transaction",
                extra={
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "location_id": location_id,
                },
            )

    except Exception as e:
        logger.error(
            f"[Square Webhook] Error handling payment.updated event: {str(e)}",
            extra={"event_id": getattr(webhook_request, "event_id", "unknown")},
        )
