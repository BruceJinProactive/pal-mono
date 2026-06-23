from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.chat.message import AuthorType, Broker, Message, Metadata, TextObject
from db.pal_repository.toast_checkout_session import ToastCheckoutSessionRepository
from db.repositories.order_repository import OrderRepository
from db.tables.types import Channel, IntegrationProvider
from services.relay_service import send_message
from tools.toast_tool._apis import create_payment_intent
from tools.toast_tool._utils import get_toast_access_token_from_aws
from tools.toast_tool.classes import PaymentIntentRequest
from tools.utils.url_shortener import shorten_url
from utils.log import logger

PAYMENT_IFRAME_ENDPOINT = "https://console.palona.ai/checkout/toast"
PAYMENT_IFRAME_TOKEN_TTL_SECONDS = 15 * 60
MAX_SMS_ORDER_SUMMARY_ITEMS = 3
SMS_BODY_MAX_CHARS = 4096
SMS_ORDER_ITEM_NAME_MAX_CHARS = 80
TRUNCATION_SUFFIX = "..."


class ToastCheckoutSessionNotFoundError(Exception):
    """Raised when a checkout session token is not found."""


class ToastCheckoutSessionExpiredError(Exception):
    """Raised when a checkout session is expired."""


class ToastCheckoutDeliveryError(Exception):
    """Raised when checkout link delivery fails."""


class ToastCheckoutPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    amount_cents: int
    tip_cents: int = 0
    external_reference_id: str
    order_external_id: str
    customer_email: str
    customer_name: str
    customer_phone: str
    order_items: list[dict[str, Any]] = Field(default_factory=list)
    toast_order_payload: dict[str, Any] | None = None
    subtotal_cents: int
    tax_cents: int
    gratuity_fees: list[dict[str, Any]] = Field(default_factory=list)
    store_id: str
    store_name: str | None = None


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: Literal["payment_checkout"]
    provider: Literal["toast"]
    payload: ToastCheckoutPayload


class ProcessCheckoutResult(BaseModel):
    token: uuid.UUID
    checkout_url: str


def _checkout_endpoint() -> str:
    return os.getenv("TOAST_CHECKOUT_IFRAME_ENDPOINT", PAYMENT_IFRAME_ENDPOINT)


def _checkout_expires_at(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current + timedelta(seconds=PAYMENT_IFRAME_TOKEN_TTL_SECONDS)


def _validate_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    expires_at = payload.get("expiresAt")
    if not isinstance(expires_at, int | float):
        raise ToastCheckoutSessionExpiredError("Checkout session missing expiration")
    if datetime.fromtimestamp(expires_at, tz=timezone.utc) < datetime.now(timezone.utc):
        raise ToastCheckoutSessionExpiredError("Checkout session expired")
    return payload


_PUBLIC_SESSION_PAYLOAD_KEYS = (
    "email",
    "name",
    "phone",
    "storeId",
    "storeName",
    "orderExternalId",
    "paymentIntentId",
    "paymentIntentExternalReferenceId",
    "subtotal",
    "tax",
    "gratuityFees",
    "total",
    "tips",
    "sessionSecret",
    "iframeBearerToken",
    "orderItems",
    "expiresAt",
)


def _build_public_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in _PUBLIC_SESSION_PAYLOAD_KEYS if key in payload}


def _build_session_payload(
    *,
    payload: ToastCheckoutPayload,
    payment_intent_id: str,
    payment_intent_external_reference_id: str,
    session_secret: str,
    payment_intent_amount: int,
    iframe_bearer_token: str,
    expires_at: datetime,
) -> dict[str, Any]:
    session_payload = {
        "email": payload.customer_email,
        "name": payload.customer_name,
        "phone": payload.customer_phone,
        "storeId": payload.store_id,
        "storeName": payload.store_name or "Restaurant",
        "orderExternalId": payload.order_external_id,
        "paymentIntentId": payment_intent_id,
        "paymentIntentExternalReferenceId": payment_intent_external_reference_id,
        "subtotal": payload.subtotal_cents,
        "tax": payload.tax_cents,
        "gratuityFees": payload.gratuity_fees,
        "total": payment_intent_amount,
        "tips": payload.tip_cents,
        "sessionSecret": session_secret,
        "iframeBearerToken": iframe_bearer_token,
        "orderItems": payload.order_items,
        "expiresAt": int(expires_at.timestamp()),
    }
    if payload.toast_order_payload is not None:
        session_payload["toastOrderPayload"] = payload.toast_order_payload
    return session_payload


def _format_payment_amount(amount_cents: int) -> str:
    dollars, cents = divmod(amount_cents, 100)
    return f"${dollars}.{cents:02d}"


def _format_order_item_quantity(quantity: Any) -> str:
    if isinstance(quantity, bool):
        return "1"
    if isinstance(quantity, int):
        return str(quantity)
    if isinstance(quantity, float) and quantity.is_integer():
        return str(int(quantity))
    if isinstance(quantity, float):
        return f"{quantity:g}"
    if isinstance(quantity, str) and quantity.strip():
        return quantity.strip()
    return "1"


def _truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= len(TRUNCATION_SUFFIX):
        return value[:max_chars]
    return value[: max_chars - len(TRUNCATION_SUFFIX)].rstrip() + TRUNCATION_SUFFIX


def _format_order_summary(
    order_items: list[dict[str, Any]],
    *,
    max_items: int = MAX_SMS_ORDER_SUMMARY_ITEMS,
) -> str:
    visible_items = order_items[:max_items]
    formatted_items: list[str] = []
    for item in visible_items:
        name = item.get("name") or item.get("item_name") or item.get("displayName")
        if not isinstance(name, str) or not name.strip():
            name = "Item"
        name = _truncate_text(name.strip(), SMS_ORDER_ITEM_NAME_MAX_CHARS)
        quantity = _format_order_item_quantity(item.get("quantity", 1))
        formatted_items.append(f"{name} x{quantity}")

    if not formatted_items:
        return "See checkout page"

    remaining_count = len(order_items) - len(visible_items)
    if remaining_count > 0:
        formatted_items.append(f"+{remaining_count} more")

    return ", ".join(formatted_items)


async def _build_checkout_url_async(token: uuid.UUID) -> str:
    return await asyncio.to_thread(
        shorten_url, f"{_checkout_endpoint()}?t={token}", use_env_url_prefix=True
    )


async def _get_or_create_checkout_session(
    *,
    session: AsyncSession,
    request: CheckoutRequest,
    conversation_id: uuid.UUID,
) -> tuple[Any, bool]:
    repo = ToastCheckoutSessionRepository(session)
    existing = await repo.get_by_external_reference_id(
        request.payload.external_reference_id
    )
    if existing is not None:
        return existing, False

    token = uuid.uuid4()
    checkout_url = await _build_checkout_url_async(token)
    row = await repo.create(
        token=token,
        conversation_id=conversation_id,
        external_reference_id=request.payload.external_reference_id,
        order_external_id=request.payload.order_external_id,
        request_payload=request.model_dump(mode="json"),
        session_payload={},
        checkout_url=checkout_url,
        expires_at=_checkout_expires_at(),
        status="processing",
    )
    await session.commit()
    await session.refresh(row)
    return row, True


async def _update_order_tracking_link_async(
    *,
    session: AsyncSession,
    payload: ToastCheckoutPayload,
    checkout_url: str,
) -> None:
    def _update(sync_session: Any) -> bool:
        order_repo = OrderRepository(sync_session, auto_commit=False)
        return (
            order_repo.update_order_by_order_id(
                store_id=payload.store_id,
                vendor=IntegrationProvider.toast,
                order_id=payload.order_external_id,
                tracking_link=checkout_url,
            )
            is not None
        )

    updated = await session.run_sync(_update)
    if not updated:
        logger.info(
            "[ToastCheckout] No persisted order found for checkout tracking link",
            extra={
                "order_external_id": payload.order_external_id,
                "store_id": payload.store_id,
            },
        )


def _build_payment_sms(
    *,
    sender_identifier: str,
    recipient_identifier: str,
    checkout_url: str,
    payload: ToastCheckoutPayload,
    broker: Broker | None = None,
) -> Message:
    store_name = payload.store_name.strip() if payload.store_name else ""
    store_name = _truncate_text(store_name, 80)
    payment_intro = (
        f"Your order at {store_name} is ready for payment."
        if store_name
        else "Your order is ready for payment."
    )
    total_line = f"Total: {_format_payment_amount(payload.amount_cents)}"
    sms_body = (
        f"{payment_intro}\n\n"
        f"{total_line}\n"
        "Order summary is available on the payment page:\n"
        f"{checkout_url}"
    )
    sms_body = _truncate_text(sms_body, SMS_BODY_MAX_CHARS)
    return Message(
        author_type=AuthorType.AGENT,
        sender_identifier=sender_identifier,
        recipient_identifier=recipient_identifier,
        channel=Channel.SMS,
        broker=broker or Broker.TWILIO,
        text=TextObject(body=sms_body),
        metadata=Metadata(testing=False),
    )


def _normalize_sms_recipient(recipient_identifier: str | None) -> str | None:
    if not recipient_identifier:
        return None

    stripped = recipient_identifier.strip()
    digits = re.sub(r"\D", "", stripped)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if stripped.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def _select_sms_recipient(
    *,
    preferred_recipient: str | None,
    fallback_recipient: str,
) -> str:
    return (
        _normalize_sms_recipient(preferred_recipient)
        or _normalize_sms_recipient(fallback_recipient)
        or fallback_recipient
    )


async def process_checkout_request_async(
    *,
    session: AsyncSession,
    checkout_request: dict[str, Any] | object,
    conversation_id: uuid.UUID,
    sender_identifier: str,
    recipient_identifier: str,
    broker: Broker | None = None,
) -> ProcessCheckoutResult:
    request = CheckoutRequest.model_validate(checkout_request)
    payload = request.payload
    repo = ToastCheckoutSessionRepository(session)
    checkout_session, created_session = await _get_or_create_checkout_session(
        session=session,
        request=request,
        conversation_id=conversation_id,
    )

    if not created_session and checkout_session.status == "ready":
        logger.info(
            "[ToastCheckout] Reusing existing checkout session",
            extra={
                "conversation_id": str(conversation_id),
                "order_external_id": payload.order_external_id,
            },
        )
        return ProcessCheckoutResult(
            token=checkout_session.token,
            checkout_url=checkout_session.checkout_url,
        )

    if not created_session and checkout_session.status == "processing":
        logger.info(
            "[ToastCheckout] Checkout request is already processing",
            extra={
                "conversation_id": str(conversation_id),
                "order_external_id": payload.order_external_id,
            },
        )
        return ProcessCheckoutResult(
            token=checkout_session.token,
            checkout_url=checkout_session.checkout_url,
        )

    if not created_session and checkout_session.status == "paid":
        logger.info(
            "[ToastCheckout] Checkout session is already paid",
            extra={
                "conversation_id": str(conversation_id),
                "order_external_id": payload.order_external_id,
            },
        )
        return ProcessCheckoutResult(
            token=checkout_session.token,
            checkout_url=checkout_session.checkout_url,
        )

    needs_payment_processing = checkout_session.status != "delivery_failed"

    try:
        if not needs_payment_processing:
            logger.info(
                "[ToastCheckout] Retrying checkout SMS delivery",
                extra={
                    "conversation_id": str(conversation_id),
                    "order_external_id": payload.order_external_id,
                },
            )
        else:
            payment_token = await asyncio.to_thread(
                get_toast_access_token_from_aws,
                token_name="TOAST_PAYMENT_CHECKOUT_ACCESS_TOKEN",
                credential_name="TOAST_PAYMENT_CHECKOUT_CLIENT_CREDENTIALS",
            )
            payment_request = PaymentIntentRequest(
                amount=payload.amount_cents,
                amountDetails={"tip": payload.tip_cents},
                currency="USD",
                externalReferenceId=payload.external_reference_id,
                captureMethod="MANUAL",
            )
            payment_intent = await asyncio.to_thread(
                create_payment_intent,
                bearer_token=payment_token,
                store_id=payload.store_id,
                payment_request=payment_request,
            )
            iframe_token = await asyncio.to_thread(
                get_toast_access_token_from_aws,
                token_name="TOAST_PAYMENT_IFRAME_ACCESS_TOKEN",
                credential_name="TOAST_PAYMENT_IFRAME_CLIENT_CREDENTIALS",
            )

            expires_at = _checkout_expires_at()
            session_payload = _build_session_payload(
                payload=payload,
                payment_intent_id=payment_intent.id,
                payment_intent_external_reference_id=payment_intent.externalReferenceId,
                session_secret=payment_intent.sessionSecret,
                payment_intent_amount=payment_intent.amount,
                iframe_bearer_token=iframe_token.access_token,
                expires_at=expires_at,
            )

            await repo.mark_ready(
                checkout_session,
                session_payload=session_payload,
                expires_at=expires_at,
            )
            await _update_order_tracking_link_async(
                session=session,
                payload=payload,
                checkout_url=checkout_session.checkout_url,
            )
            await session.commit()
            await session.refresh(checkout_session)
    except Exception:
        await repo.mark_failed(checkout_session, status="failed")
        await session.commit()
        raise

    if not needs_payment_processing:
        await repo.mark_ready(
            checkout_session,
            session_payload=checkout_session.session_payload,
            expires_at=checkout_session.expires_at,
        )
        await session.commit()
        await session.refresh(checkout_session)

    try:
        sms = _build_payment_sms(
            sender_identifier=sender_identifier,
            recipient_identifier=_select_sms_recipient(
                preferred_recipient=payload.customer_phone,
                fallback_recipient=recipient_identifier,
            ),
            checkout_url=checkout_session.checkout_url,
            payload=payload,
            broker=broker,
        )
        send_result = await asyncio.to_thread(send_message, sms)
        if (
            not isinstance(send_result, dict)
            or send_result.get("status") != "scheduled"
        ):
            raise ToastCheckoutDeliveryError("Checkout SMS delivery failed")
    except Exception:
        await repo.mark_failed(checkout_session, status="delivery_failed")
        await session.commit()
        raise

    logger.info(
        "[ToastCheckout] Payment link SMS scheduled",
        extra={
            "conversation_id": str(conversation_id),
            "order_external_id": payload.order_external_id,
            "send_status": (
                send_result.get("status") if isinstance(send_result, dict) else None
            ),
        },
    )
    return ProcessCheckoutResult(
        token=checkout_session.token,
        checkout_url=checkout_session.checkout_url,
    )


async def get_checkout_session_payload_async(
    session: AsyncSession,
    token: uuid.UUID,
) -> dict[str, Any]:
    repo = ToastCheckoutSessionRepository(session)
    checkout_session = await repo.get_by_token(token)
    if checkout_session is None or checkout_session.status != "ready":
        raise ToastCheckoutSessionNotFoundError("Checkout session not found")
    session_payload = _validate_session_payload(dict(checkout_session.session_payload))
    return _build_public_session_payload(session_payload)
