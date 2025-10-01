import base64
import os
import uuid
from datetime import UTC, datetime
from typing import Optional

import requests
from docusign_esign import (
    ApiClient,
    Document,
    EnvelopeDefinition,
    EnvelopesApi,
    Recipients,
    RecipientViewRequest,
    Signer,
    SignHere,
    Tabs,
)
from docusign_esign.client.api_exception import ApiException
from sqlalchemy.orm import Session

from db import AccountRepository
from db.tables.accounts import Account
from utils.log import logger

from ._config import get_docusign_config, validate_config


def _get_jwt_token() -> tuple[str, str]:
    """
    Get JWT access token and account base URI for DocuSign API.

    Returns:
        tuple: (access_token, base_uri)
    """
    config = get_docusign_config()

    is_valid, error_msg = validate_config()
    if not is_valid:
        raise ValueError(f"Invalid DocuSign configuration: {error_msg}")

    api_client = ApiClient()
    api_client.set_base_path(config["base_path"])
    api_client.set_oauth_host_name(config["oauth_host"])

    try:
        private_key = config["private_key"].replace("\\n", "\n")

        response = api_client.request_jwt_user_token(
            client_id=config["integration_key"],
            user_id=config["user_id"],
            oauth_host_name=config["oauth_host"],
            private_key_bytes=private_key.encode(),
            expires_in=3600,
            scopes=["signature", "impersonation"],
        )

        access_token = response.access_token  # type: ignore

        user_info = api_client.get_user_info(access_token)

        if not user_info.accounts or len(user_info.accounts) == 0:  # type: ignore
            raise ValueError("No DocuSign accounts found for this user")

        account = user_info.accounts[0]  # type: ignore

        if config["account_id"]:
            for acc in user_info.accounts:  # type: ignore
                if acc.account_id == config["account_id"]:  # type: ignore
                    account = acc
                    break

        base_uri = account.base_uri + "/restapi"  # type: ignore

        return access_token, base_uri
    except Exception as e:
        logger.error(f"Failed to get JWT token: {str(e)}")
        raise


def _create_api_client(access_token: str, base_uri: str) -> ApiClient:
    """Create configured API client with account-specific base URI."""
    api_client = ApiClient()
    api_client.host = base_uri
    api_client.set_base_path(base_uri)
    api_client.set_default_header("Authorization", f"Bearer {access_token}")
    return api_client


def _make_envelope(
    document_name: str,
    signer_email: str,
    signer_name: str,
    signer_client_id: str,
    email_subject: str,
    document_content: Optional[bytes] = None,
    remote_url: Optional[str] = None,
) -> EnvelopeDefinition:
    """Create an envelope definition for terms signing."""
    if document_content:
        base64_content = base64.b64encode(document_content).decode("ascii")
        document = Document(
            document_base64=base64_content,
            name=document_name,
            file_extension="pdf",
            document_id="1",
        )
    elif remote_url:
        document = Document(
            remote_url=remote_url,
            name=document_name,
            file_extension="pdf",
            document_id="1",
        )
    else:
        raise ValueError("Either document_content or remote_url must be provided")

    signer = Signer(
        email=signer_email,
        name=signer_name,
        recipient_id="1",
        routing_order="1",
        client_user_id=signer_client_id,
    )

    sign_here = SignHere(
        anchor_string="/sn1/",
        anchor_units="pixels",
        anchor_y_offset="10",
        anchor_x_offset="20",
    )

    signer.tabs = Tabs(sign_here_tabs=[sign_here])

    envelope_definition = EnvelopeDefinition(
        email_subject=email_subject,
        documents=[document],
        recipients=Recipients(signers=[signer]),
        status="sent",
    )

    return envelope_definition


def initiate_terms_signing(
    account: Account,
    signer_name: str,
    signer_email: str,
    redirect_url: str,
    frame_ancestors: Optional[list[str]] = None,
) -> dict:
    """
    Initiate terms of service signing for an account.

    Args:
        account: Account instance
        signer_name: Name of the person signing
        signer_email: Email of the person signing
        redirect_url: URL to redirect after signing
        frame_ancestors: Frame ancestors for focused view

    Returns:
        dict: Contains envelope_id, signing_url, signer_client_user_id

    Raises:
        Exception: If terms signing initiation fails
    """
    config = get_docusign_config()
    docusign_account_id = config["account_id"]

    pdf_url = os.getenv("DOCUSIGN_TERMS_PDF_URL")

    if not pdf_url:
        raise ValueError(
            "DOCUSIGN_TERMS_PDF_URL environment variable not set. "
            "Please configure it in your .env file."
        )

    logger.info(f"Using terms PDF from URL: {pdf_url}")

    try:
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()
        document_content = response.content
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch terms PDF from {pdf_url}: {str(e)}")

    signer_client_id = str(uuid.uuid4())

    # Always enforce server-allowlisted origins
    frame_ancestors = [config["frame_ancestor"]]

    message_origins = [config["message_origin"]]

    try:
        access_token, base_uri = _get_jwt_token()

        api_client = _create_api_client(access_token, base_uri)
        envelopes_api = EnvelopesApi(api_client)

        envelope_definition = _make_envelope(
            document_name="Terms of Service Agreement",
            signer_email=signer_email,
            signer_name=signer_name,
            signer_client_id=signer_client_id,
            email_subject=f"Please sign Terms of Service for {account.display_name or account.name}",
            document_content=document_content,
            remote_url=None,
        )

        envelope_summary = envelopes_api.create_envelope(
            account_id=docusign_account_id,
            envelope_definition=envelope_definition,
        )

        envelope_id = envelope_summary.envelope_id
        logger.info(f"Created DocuSign envelope for {account.name}: {envelope_id}")

        recipient_view_request = RecipientViewRequest(
            authentication_method="none",
            client_user_id=signer_client_id,
            recipient_id="1",
            return_url=redirect_url,
            user_name=signer_name,
            email=signer_email,
            frame_ancestors=frame_ancestors,
            message_origins=message_origins,
        )

        recipient_view = envelopes_api.create_recipient_view(
            account_id=docusign_account_id,
            envelope_id=envelope_id,
            recipient_view_request=recipient_view_request,
        )

        signing_url = recipient_view.url
        logger.info(f"Created signing URL for envelope: {envelope_id}")

        return {
            "success": True,
            "envelope_id": envelope_id,
            "signing_url": signing_url,
            "signer_client_user_id": signer_client_id,
        }

    except ApiException as e:
        logger.error(f"DocuSign API error: {e}")
        raise Exception("Failed to create signature request")
    except Exception as e:
        logger.error(f"Error creating signature request: {str(e)}")
        raise


def complete_terms_signing(
    session: Session,
    account_id: uuid.UUID,
    envelope_id: str,
) -> Account:
    """
    Mark terms as accepted after successful DocuSign signing.

    Args:
        session: Database session
        account_id: Account UUID
        envelope_id: DocuSign envelope ID

    Returns:
        Updated Account instance

    Raises:
        ValueError: If account not found or envelope mismatch
    """
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(account_id)

    if not account:
        raise ValueError(f"Account not found: {account_id}")

    if account.terms_envelope_id and account.terms_envelope_id != envelope_id:
        raise ValueError(
            f"Envelope ID mismatch for account {account.name}. "
            f"Expected {account.terms_envelope_id}, got {envelope_id}"
        )

    status_info = get_envelope_status(envelope_id)
    if status_info.get("status") != "completed":
        raise ValueError("Envelope is not completed yet")

    updated_account = account_repo.update_account(
        account_name=account.name,
        terms_accepted=True,
        terms_envelope_id=envelope_id,
        terms_signed_at=datetime.now(UTC),
    )

    if not updated_account:
        raise ValueError(f"Failed to update account {account.name}")

    logger.info(
        f"Marked terms as accepted for account {updated_account.name}, envelope: {envelope_id}"
    )

    return updated_account


def get_envelope_status(envelope_id: str) -> dict:
    """
    Get the current status of a DocuSign envelope.

    Args:
        envelope_id: DocuSign envelope ID

    Returns:
        dict: Envelope status information

    Raises:
        Exception: If status retrieval fails
    """
    config = get_docusign_config()
    docusign_account_id = config["account_id"]

    try:
        access_token, base_uri = _get_jwt_token()
        api_client = _create_api_client(access_token, base_uri)
        envelopes_api = EnvelopesApi(api_client)

        envelope = envelopes_api.get_envelope(
            account_id=docusign_account_id,
            envelope_id=envelope_id,
        )

        return {
            "envelope_id": envelope_id,
            "status": envelope.status,
            "created_date_time": getattr(envelope, "created_date_time", None),
            "sent_date_time": getattr(envelope, "sent_date_time", None),
            "delivered_date_time": getattr(envelope, "delivered_date_time", None),
            "completed_date_time": getattr(envelope, "completed_date_time", None),
            "declined_date_time": getattr(envelope, "declined_date_time", None),
            "voided_date_time": getattr(envelope, "voided_date_time", None),
            "status_changed_date_time": getattr(
                envelope, "status_changed_date_time", None
            ),
        }

    except ApiException as e:
        logger.error(f"DocuSign API error getting envelope status: {e}")
        raise Exception("Failed to get envelope status")
    except Exception as e:
        logger.error(f"Error getting envelope status: {str(e)}")
        raise


def check_terms_status(account: Account) -> dict:
    """
    Check the status of terms acceptance for an account.

    Args:
        account: Account instance

    Returns:
        dict: Terms status information
    """
    status = {
        "account_id": str(account.id),
        "account_name": account.name,
        "terms_accepted": account.terms_accepted,
        "terms_envelope_id": account.terms_envelope_id,
        "terms_signed_at": (
            account.terms_signed_at.isoformat() if account.terms_signed_at else None
        ),
    }

    if account.terms_envelope_id and not account.terms_accepted:
        try:
            envelope_status = get_envelope_status(account.terms_envelope_id)
            status["envelope_status"] = envelope_status["status"]
            status["envelope_sent_date"] = envelope_status.get("sent_date_time")
        except Exception as e:
            logger.warning(f"Could not fetch envelope status: {e}")
            status["envelope_status"] = "unknown"

    return status
