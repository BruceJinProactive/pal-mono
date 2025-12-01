import json
from datetime import datetime, timezone
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from db.tables import Integration, IntegrationProvider, Project, ProjectIntegration
from services.knowledge_service import (
    delete_knowledge_file_by_metadata,
    query_vector_database,
    upload_knowledge_file,
)
from tools.toast_tool._apis import (
    connect_toast_order_hub,
    get_existing_order,
    post_payment_to_order,
    update_payment_intent,
)
from tools.toast_tool._utils import get_toast_access_token_from_aws
from tools.toast_tool.classes import ToastPayment
from tools.utils.ordering.classes import HttpMethod
from utils.log import logger

from ._utils import (
    process_partner_event,
    update_menu_content,
    update_ordering_schedule,
    update_stock_item_status,
)
from .schema import ToastWebhookRequest, ToastWebhookResponse

# Constants for payment iframe token encryption
HARD_CODED_PAYMENT_IFRAME_SECRET = "xK8dP2m_QrZ7vN4wL9cF3bJ6hT5yU1gS0aE8iO-pMxA="


@lru_cache(maxsize=1)
def _get_payment_iframe_fernet() -> Fernet:
    """Get cached Fernet instance for decrypting payment tokens."""
    try:
        return Fernet(HARD_CODED_PAYMENT_IFRAME_SECRET.encode("utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid encryption configuration",
        ) from exc


async def get_checkout_session(token: str) -> JSONResponse:
    """
    Decrypt and return the payment session payload.

    This endpoint decrypts the Fernet-encrypted token passed in the URL
    and returns the full payment payload including orderItems.

    Args:
        token: URL-encoded Fernet encrypted token

    Returns:
        JSONResponse with decrypted payload
    """
    logger.debug("[Toast] get_checkout_session: Received token request")

    try:
        # Decrypt without TTL validation (Fernet will still check signature)
        decrypted = _get_payment_iframe_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        logger.warning("[Toast] get_checkout_session: Invalid token", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"
        ) from exc

    try:
        payload = json.loads(decrypted.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.error(
            "[Toast] get_checkout_session: Failed to decode payload", exc_info=exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed token payload"
        ) from exc

    # Validate expiration from payload
    expires_at = payload.get("expiresAt")
    if not expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing expiration",
        )

    # Check if token has expired using the expiresAt timestamp from payload
    if datetime.fromtimestamp(expires_at, tz=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token expired",
        )

    logger.debug(
        "[Toast] get_checkout_session: Token validated successfully",
        extra={
            "store_id": payload.get("storeId"),
            "order_external_id": payload.get("orderExternalId"),
            "order_items_count": len(payload.get("orderItems", [])),
        },
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)


def _are_dining_options_same(
    api_response_raw: str, kb_dining_options_text: str
) -> bool:
    """
    Compare dining options raw response from Toast API with those stored in KB.

    Args:
        api_response_raw: Raw string response from Toast API
        kb_dining_options_text: String containing raw dining options from KB

    Returns:
        bool: True if dining options are same, False if they are different
    """
    try:
        # Direct string comparison since both should be the same raw format
        return api_response_raw.strip() == kb_dining_options_text.strip()

    except Exception as e:
        logger.error(
            f"[ToastAPIIntegration._are_dining_options_same] Error comparing dining options: {e}"
        )
        # On error, assume they are different
        return False


async def api_toast_webhook(request: Request) -> JSONResponse:
    """
    Process incoming webhook requests from Toast.
    Authentication and validation are handled by AWS API Gateway.

    Args:
        request: The FastAPI request object

    Returns:
        JSONResponse: The response to send back to Toast

    Raises:
        HTTPException: If there's an error processing the request
    """
    # Extract body from request
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid JSON in request body: {str(e)}"},
        )

    # Validate request body against schema
    try:
        webhook_request = ToastWebhookRequest(**body)

        # Handle webhook events
        match webhook_request.eventCategory:
            case "menus":
                await update_menu_content(webhook_request)
            case "stock":
                await update_stock_item_status(webhook_request)
            case "ordering_schedule":
                await update_ordering_schedule(webhook_request)
            case "partner":
                await process_partner_event(webhook_request)
            case _:
                logger.warning(
                    f"[ToastWebhook.api_toast_webhook] Received unknown Toast webhook event category: {webhook_request.eventCategory}"
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=ToastWebhookResponse().model_dump(exclude_none=True),
                )
    except ValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid request body: {str(e)}"},
        )

    # Log the incoming request for debugging
    logger.debug(
        "[ToastWebhook.api_toast_webhook] Toast webhook request received",
        extra={
            "timestamp": webhook_request.timestamp,
            "event_category": webhook_request.eventCategory,
            "event_type": webhook_request.eventType,
            "guid": webhook_request.guid,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ToastWebhookResponse().model_dump(exclude_none=True),
    )


def _fetch_dining_options(integration: Integration) -> str | None:
    """Fetch dining options from Toast API for given integration."""
    if not integration.business_id:
        logger.warning(
            "[ToastAPIIntegration._fetch_dining_options] Integration has no business ID, skipping"
        )
        return None

    try:
        bearer_token = get_toast_access_token_from_aws()
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/config/v2/diningOptions",
            store_id=integration.business_id,
            query_params=None,
            payload=None,
        )

        if response.status != 200:
            raise Exception(f"Toast API returned status {response.status}")

        return response.decoded_body

    except Exception as e:
        logger.error(
            "[ToastAPIIntegration._fetch_dining_options] Failed to fetch dining options for store %s: %s",
            integration.business_id,
            e.__class__.__name__,
            exc_info=True,
        )
        return None


def _upload_dining_options_to_kb(
    index_name: str, namespace: str, dining_options_raw: str
):
    """Upload dining options to knowledge base."""
    upload_knowledge_file(
        index_name=index_name,
        namespace=namespace,
        file_name="dining_options.txt",
        content=dining_options_raw.encode("utf-8"),
        metadata={"isDiningOptions": True},
    )


def _refresh_dining_options_in_kb(
    index_name: str, namespace: str, dining_options_raw: str
):
    """Delete existing dining options and upload new ones."""
    delete_knowledge_file_by_metadata(
        index_name=index_name,
        namespace=namespace,
        metadata={"isDiningOptions": {"$eq": True}},
    )
    _upload_dining_options_to_kb(index_name, namespace, dining_options_raw)


def _update_project_dining_options(
    project: Project, integration: Integration, dining_options_raw: str
):
    """Update dining options in project's knowledge base if needed."""
    raw_config = project.raw_config
    project_tools = raw_config.get("tools", {}).get("identifiers", [])

    for project_tool in project_tools:
        if project_tool.get("tool_name") != "toast_tool":
            continue

        namespace = project_tool.get("namespace")
        index_name = project_tool.get("index_name")

        if not (namespace and index_name):
            continue

        # Query KB for existing dining options
        result = query_vector_database(
            index_name=index_name,
            namespace=namespace,
            query="dining options",
            top_k=3,
        )

        if not result:
            logger.warning(
                "[ToastAPIIntegration._update_project_dining_options] No KB result; refreshing from API for store %s",
                integration.business_id,
            )
            _upload_dining_options_to_kb(index_name, namespace, dining_options_raw)
            return

        # Look for existing dining options
        for match in result:
            match_metadata = match.get("metadata", {})
            if not match_metadata.get("isDiningOptions", False):
                continue

            logger.debug(
                "[ToastAPIIntegration._update_project_dining_options] Dining options found in KB for store %s with metadata %s",
                integration.business_id,
                match_metadata,
            )

            kb_dining_options = match_metadata.get("text")
            if not kb_dining_options:
                logger.warning(
                    "[ToastAPIIntegration._update_project_dining_options] KB match missing text; re-uploading for store %s",
                    integration.business_id,
                )
                _refresh_dining_options_in_kb(index_name, namespace, dining_options_raw)
                return

            # Compare and update if different
            if not _are_dining_options_same(dining_options_raw, kb_dining_options):
                logger.debug(
                    "[ToastAPIIntegration._update_project_dining_options] Updating dining options for store %s",
                    integration.business_id,
                )
                _refresh_dining_options_in_kb(index_name, namespace, dining_options_raw)
            else:
                logger.debug(
                    "[ToastAPIIntegration._update_project_dining_options] Dining options match for store %s",
                    integration.business_id,
                )
            return

        # No dining options found, create new ones
        logger.debug(
            "[ToastAPIIntegration._update_project_dining_options] No dining options found; creating for store %s",
            integration.business_id,
        )
        _refresh_dining_options_in_kb(index_name, namespace, dining_options_raw)


def check_and_refresh_dining_options(session):
    """Check and refresh dining options for all Toast integrations."""
    integrations = (
        session.query(Integration)
        .filter(Integration.provider == IntegrationProvider.toast)
        .all()
    )

    for integration in integrations:
        dining_options_raw = _fetch_dining_options(integration)
        if not dining_options_raw:
            continue

        projects = (
            session.query(Project)
            .join(ProjectIntegration)
            .filter(ProjectIntegration.integration_id == integration.id)
            .all()
        )

        for project in projects:
            _update_project_dining_options(project, integration, dining_options_raw)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Dining options successfully checked"},
    )


async def checkout_complete(request: Request) -> JSONResponse:
    """
    Process incoming checkout requests from Toast Iframe.
    Authentication and validation are handled by AWS API Gateway.

    Args:
        request: The FastAPI request object

    Returns:
        JSONResponse: The response to send back to Toast Iframe UI
    """
    # Retrieve store ID, order External ID, payment external reference ID from request body
    try:
        body = await request.json()
        store_id = body.get("storeId")
        order_external_id = body.get("orderExternalId")
        payment_external_reference_id = body.get("paymentExternalReferenceId")
        # All amounts from frontend are in cents (integers) to avoid rounding errors
        charged_amount_cents = body.get(
            "chargedAmountCents"
        )  # Total charged in cents (includes tip)
        tip_amount_cents = body.get("tipAmountCents", 0)  # Tip amount in cents
        test_mode = body.get("testMode", False)

        logger.debug(
            f"[ToastAPIIntegration.checkout_complete] Processing checkout request for store {store_id}, "
            f"order {order_external_id}, payment {payment_external_reference_id}, "
            f"chargedAmountCents {charged_amount_cents}, tipAmountCents {tip_amount_cents}, testMode {test_mode}"
        )

        if not (store_id and order_external_id and payment_external_reference_id):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Missing required fields: storeId, orderExternalId, paymentExternalReferenceId"
                },
            )
        if test_mode:
            toast_bearer_token = get_toast_access_token_from_aws(
                token_api_endpoint="ws-sandbox-api.eng.toasttab.com",
                token_name="TOAST_SANDBOX_ACCESS_TOKEN",
                credential_name="TOAST_SANDBOX_CLIENT_CREDENTIALS",
            )
        else:
            toast_bearer_token = get_toast_access_token_from_aws()

        # 1. Fetch order details from Toast API using order_external_id
        logger.debug(
            f"[ToastAPIIntegration.checkout_complete] getting order with external_id: {order_external_id}"
        )
        try:
            order = get_existing_order(
                toast_bearer_token,
                store_id,
                order_external_id,
                general_api_endpoint=(
                    "ws-sandbox-api.eng.toasttab.com" if test_mode else None
                ),
            )
        except Exception as e:
            logger.error(
                f"[ToastAPIIntegration.checkout_complete] error getting order: {e}"
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": f"Failed to get order: {str(e)}"},
            )
        if not order:
            logger.error(
                f"[ToastAPIIntegration.checkout_complete] order {order_external_id} not found"
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": f"Order with ID {order_external_id} not found, cannot add payment to order. Contact the store owner to verify the order exists."
                },
            )
        logger.debug(
            f"[checkout_complete] Retrieved order {order.guid} with {len(order.checks)} check(s)"
        )

        if not order.checks or len(order.checks) == 0:
            logger.error(
                f"[ToastAPIIntegration.checkout_complete] order {order_external_id} has no checks"
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": f"Order with ID {order_external_id} has no checks, cannot add payment to order. Contact the store owner to verify the order exists."
                },
            )
        if not hasattr(order.checks[0], "guid") or not getattr(order.checks[0], "guid"):
            logger.error(
                f"[ToastAPIIntegration.checkout_complete] order {order_external_id} check has no guid"
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": f"Order with ID {order_external_id} has no valid check GUID"
                },
            )

        # 2. Get the first check's payment list
        first_check = order.checks[0]
        logger.debug(f"[ToastAPIIntegration.checkout_complete] first check guid: {first_check.guid}")  # type: ignore
        logger.debug(
            f"[ToastAPIIntegration.checkout_complete] first check has payments attr: {hasattr(first_check, 'payments')}"
        )
        if hasattr(first_check, "payments"):
            logger.debug(
                f"[ToastAPIIntegration.checkout_complete] first check payments: {first_check.payments}"
            )
            logger.debug(
                f"[ToastAPIIntegration.checkout_complete] first check payments length: {len(first_check.payments) if first_check.payments else 0}"
            )

        # 3. Construct a new payment object with required fields
        # Use the proper ToastPayment class to ensure correct format
        logger.debug(f"[ToastAPIIntegration.checkout_complete] first check amount: {first_check.amount}")  # type: ignore
        logger.debug(f"[ToastAPIIntegration.checkout_complete] first check totalAmount: {first_check.totalAmount}")  # type: ignore

        # Verify charged amount matches expected amount (order total + tip)
        # All amounts are in cents to avoid rounding errors
        amount_mismatch = False
        order_total_cents = round(first_check.totalAmount * 100)  # type: ignore - convert dollars to cents

        if charged_amount_cents is not None:
            # Derive order amount from charged amount (source of truth from Toast)
            order_amount_cents = charged_amount_cents - tip_amount_cents
            expected_charged_cents = order_total_cents + tip_amount_cents

            if charged_amount_cents != expected_charged_cents:
                logger.warning(
                    f"[ToastAPIIntegration.checkout_complete] Amount mismatch! "
                    f"Charged: {charged_amount_cents} cents, Expected: {expected_charged_cents} cents "
                    f"(order_total_cents: {order_total_cents}, tip_amount_cents: {tip_amount_cents}, "
                    f"derived_order_amount_cents: {order_amount_cents})"
                )
                amount_mismatch = True
            else:
                logger.debug(
                    f"[ToastAPIIntegration.checkout_complete] Amount verified: {charged_amount_cents} cents "
                    f"(order: {order_amount_cents}, tip: {tip_amount_cents})"
                )
        else:
            # Fallback if charged_amount_cents not provided
            order_amount_cents = order_total_cents
            logger.warning(
                "[ToastAPIIntegration.checkout_complete] chargedAmountCents not provided, "
                f"using order total from Toast API: {order_total_cents} cents"
            )

        # Convert cents to dollars for ToastPayment (Toast API expects dollars)
        order_amount_dollars = order_amount_cents / 100
        tip_amount_dollars = tip_amount_cents / 100

        # Create payment using ToastPayment class
        # amount is the order amount EXCLUDING tip (per ToastPayment model definition)
        payment = ToastPayment(
            amount=order_amount_dollars,
            entityType=None,  # Response-only field, not needed for creation
            guid=payment_external_reference_id,  # Use external reference ID as GUID
            tipAmount=tip_amount_dollars,
            type="CREDIT",
            externalId="TPC-PALONA:" + payment_external_reference_id,
        )
        logger.debug(
            f"[ToastAPIIntegration.checkout_complete] constructed payment object: {payment.model_dump(exclude_none=True)}"
        )

        logger.debug(
            f"[ToastAPIIntegration.checkout_complete] posting payment to order {order.guid}, check {first_check.guid}"  # type: ignore
        )

        # 4. Post payment to the check using the proper function
        post_payment_to_order(
            bearer_token=toast_bearer_token,
            store_id=store_id,
            order_guid=order.guid,  # type: ignore
            check_guid=first_check.guid,  # type: ignore
            payment=payment,
            general_api_endpoint=(
                "ws-sandbox-api.eng.toasttab.com" if test_mode else None
            ),
        )
        logger.debug(
            f"[ToastAPIIntegration.checkout_complete] Successfully posted payment with externalId {payment_external_reference_id} to order {order.guid}"  # type: ignore
        )

        # 4. Return success response to Toast Iframe UI
        response_content = {
            "message": "Payment processed successfully",
            "testMode": test_mode,
            "amountMismatch": amount_mismatch,
        }
        if amount_mismatch:
            response_content["warning"] = (
                "Amount mismatch detected. Please contact the store to verify your order."
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_content,
        )

    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid JSON in request body: {str(e)}"},
        )
    except Exception as e:
        logger.error(
            f"[ToastAPIIntegration.checkout_complete] Unexpected error: {str(e)}",
            exc_info=True,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Internal server error processing checkout: {str(e)}"},
        )


async def update_tip(request: Request) -> JSONResponse:
    """
    Update the tip amount on an existing payment intent.
    This endpoint is called when the customer changes their tip selection.

    Args:
        request: The FastAPI request object containing:
            - storeId: The Toast store ID
            - paymentIntentId: The payment intent ID to update
            - baseAmount: The base order amount in cents (without tip)
            - tipAmount: The new tip amount in cents
            - testMode: Whether to use sandbox environment

    Returns:
        JSONResponse: Success status or error message
    """
    try:
        body = await request.json()
        store_id = body.get("storeId")
        payment_intent_id = body.get("paymentIntentId")
        base_amount = body.get("baseAmount")
        tip_amount = body.get("tipAmount", 0)
        test_mode = body.get("testMode", False)

        logger.debug(
            f"[ToastAPIIntegration.update_tip] Updating tip for store {store_id}, "
            f"payment intent {payment_intent_id}, base {base_amount}, tip {tip_amount}"
        )

        if not (store_id and payment_intent_id and base_amount is not None):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Missing required fields: storeId, paymentIntentId, baseAmount"
                },
            )

        # Get the hosted payment checkout bearer token
        if test_mode:
            toast_bearer_token = get_toast_access_token_from_aws(
                token_api_endpoint="ws-sandbox-api.eng.toasttab.com",
                token_name="TOAST_PAYMENT_CHECKOUT_ACCESS_TOKEN",
                credential_name="TOAST_PAYMENT_CHECKOUT_CLIENT_CREDENTIALS",
            )
        else:
            toast_bearer_token = get_toast_access_token_from_aws(
                token_name="TOAST_PAYMENT_CHECKOUT_ACCESS_TOKEN",
                credential_name="TOAST_PAYMENT_CHECKOUT_CLIENT_CREDENTIALS",
            )

        # Calculate total amount (base + tip)
        total_amount = base_amount + tip_amount

        # Update the payment intent with new amount and tip
        update_payment_intent(
            bearer_token=toast_bearer_token,
            store_id=store_id,
            payment_intent_id=payment_intent_id,
            amount=total_amount,
            tip_amount=tip_amount,
            payments_api_endpoint=(
                "payments-sandbox.toasttab.com" if test_mode else None
            ),
        )

        logger.debug(
            f"[ToastAPIIntegration.update_tip] Successfully updated payment intent {payment_intent_id}"
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Tip updated successfully",
                "totalAmount": total_amount,
                "tipAmount": tip_amount,
            },
        )

    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid request: {str(e)}"},
        )
    except Exception as e:
        logger.error(
            f"[ToastAPIIntegration.update_tip] Unexpected error: {str(e)}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Internal server error updating tip: {str(e)}"},
        )
