"""
Order Service

A generic service for managing order data across all integration providers.
Provides a standardized way to save, retrieve, and update order records
from tools like Adora, Square, Toast, Olo, OpenTable, etc.
"""

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from db.tables.orders import Order
from db.tables.types import IntegrationProvider

from . import _implementation
from ._utils import reconstruct_order_items
from .schema import OrderData

OrderStatusUpdateResult = _implementation.OrderStatusUpdateResult


async def get_toast_checkout_session_snapshot(
    external_reference_id: str,
) -> tuple[str | None, dict[str, Any], str | None]:
    """
    Return checkout session status, payload, and order external ID.

    The returned values are detached from the DB session so callers do not hold
    a transaction while performing external API work.
    """
    return await _implementation.get_toast_checkout_session_snapshot(
        external_reference_id
    )


async def claim_toast_checkout_session_processing(
    external_reference_id: str,
) -> str | None:
    """
    Atomically claim a ready Toast checkout session for processing.

    Returns "claimed" when this caller won the claim, the existing session
    status when another request already claimed or completed it, or None when
    no checkout session exists.
    """
    return await _implementation.claim_toast_checkout_session_processing(
        external_reference_id
    )


async def mark_toast_checkout_session_paid(external_reference_id: str) -> None:
    """Mark a Toast checkout session paid if it exists."""
    await _implementation.mark_toast_checkout_session_paid(external_reference_id)


def create_order(
    session: Session,
    order_data: OrderData,
) -> Order:
    """
    Create or return an order record from standardized order data.

    Args:
        session: Database session
        order_data: Standardized order data

    Returns:
        Order: The created order record, or the existing row for this order identity
    """
    return _implementation.create_order(session, order_data)


def save_order(
    tool_metadata,
    vendor,
    order_id=None,
    store_id=None,
    status="pending",
    fulfillment_strategy=None,
    subtotal=None,
    order_items=None,
    order_time=None,
    tracking_link=None,
    session=None,
):
    """
    Save an order to the orders table - convenience function for tools.

    Args:
        tool_metadata: Tool metadata containing session_id
        vendor: The integration provider
        order_id: Order identifier from external system
        store_id: Store/location identifier
        status: Order status (default: "pending")
        fulfillment_strategy: Strategy for fulfilling the order
        subtotal: Order subtotal amount
        order_items: List of ordered items
        order_time: When the order occurred
        tracking_link: Link to track the order
        session: Optional database session

    Returns:
        uuid.UUID: The ID of the created order, or None if failed
    """
    return _implementation.save_order(
        tool_metadata=tool_metadata,
        vendor=vendor,
        order_id=order_id,
        store_id=store_id,
        status=status,
        fulfillment_strategy=fulfillment_strategy,
        subtotal=subtotal,
        order_items=order_items,
        order_time=order_time,
        tracking_link=tracking_link,
        session=session,
    )


def update_order_by_order_id(
    store_id,
    vendor,
    new_status,
    order_id=None,
    tracking_link=None,
    session=None,
):
    """
    Update an order by its order ID - helper function for async contexts.

    Args:
        store_id: The store ID to find
        vendor: The integration provider
        new_status: The new status to set
        order_id: The order ID to find
        tracking_link: Optional new tracking link to set
        session: Optional database session

    Returns:
        bool: True if order was found and updated, False otherwise
    """
    return _implementation.update_order_by_order_id(
        store_id=store_id,
        vendor=vendor,
        new_status=new_status,
        order_id=order_id,
        tracking_link=tracking_link,
        session=session,
    )


def update_order_by_phone(
    store_id,
    vendor,
    new_status,
    user_phone_number,
    order_date,
    tracking_link=None,
):
    """
    Update an order by user phone number and order date.

    This method is specifically designed for updating orders when the order_id
    is not available, using phone number and date for matching instead.

    Args:
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        new_status: The new status to set
        user_phone_number: The user's phone number for matching
        order_date: The date of the order for matching
        tracking_link: Optional new tracking link to set

    Returns:
        bool: True if order was found and updated, False otherwise
    """
    return _implementation.update_order_by_phone(
        store_id=store_id,
        vendor=vendor,
        new_status=new_status,
        user_phone_number=user_phone_number,
        order_date=order_date,
        tracking_link=tracking_link,
    )


def update_order_from_webhook(
    store_id: str,
    vendor: IntegrationProvider,
    new_status: str,
    order_id: str | None = None,
    alternate_order_id: str | None = None,
    user_phone_number: str | None = None,
    order_date: Any = None,
    tracking_link: str | None = None,
) -> OrderStatusUpdateResult | None:
    """
    Update an order from a POS webhook using external IDs first.

    Args:
        store_id: Store/location identifier.
        vendor: Integration provider.
        new_status: New status to set.
        order_id: Primary external order identifier.
        alternate_order_id: Secondary external order identifier.
        user_phone_number: Customer phone fallback.
        order_date: Order date fallback.
        tracking_link: Optional tracking link to set.

    Returns:
        OrderStatusUpdateResult | None: Updated order snapshot, if found.
    """
    return _implementation.update_order_from_webhook(
        store_id=store_id,
        vendor=vendor,
        new_status=new_status,
        order_id=order_id,
        alternate_order_id=alternate_order_id,
        user_phone_number=user_phone_number,
        order_date=order_date,
        tracking_link=tracking_link,
    )


def get_order_by_id(
    session: Session,
    order_id: uuid.UUID,
) -> Optional[Order]:
    """
    Get an order by its ID.

    Args:
        session: Database session
        order_id: The ID of the order to retrieve

    Returns:
        Order | None: The order if found, None otherwise
    """
    return _implementation.get_order_by_id(session, order_id)


def get_order_by_order_id_store_vendor(
    order_id: str,
    store_id: str,
    vendor,
    session: Optional[Session] = None,
) -> Optional[Order]:
    """
    Get an order by its external order ID, store ID, and vendor.

    Args:
        order_id: The external order ID to find
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        session: Optional database session (creates one if not provided)

    Returns:
        Order: The order if found, or None if not found
    """
    return _implementation.get_order_by_order_id_store_vendor(
        order_id=order_id,
        store_id=store_id,
        vendor=vendor,
        session=session,
    )


def create_order_from_agent_async(
    session,
    order_details,
    conversation_id,
):
    """
    Create an order from pal-agents order_details with duplicate checking.

    This async function handles all type conversions, duplicate checking, and order
    creation for orders received from the AI agent. It's idempotent - calling
    it multiple times with the same order_details will only create one order.

    Args:
        session: Async database session
        order_details: Order details object from pal-agents
        conversation_id: The conversation ID this order belongs to

    Returns:
        Order | None: The created order, existing row, or None if creation fails
    """
    return _implementation.create_order_from_agent_async(
        session, order_details, conversation_id
    )


__all__ = [
    # Core order operations
    "create_order",
    "create_order_from_agent_async",
    "get_order_by_id",
    "get_order_by_order_id_store_vendor",
    # Helper functions for tools
    "save_order",
    "update_order_by_order_id",
    "update_order_from_webhook",
    "update_order_by_phone",
    "reconstruct_order_items",
    # Data schemas
    "OrderData",
    "OrderStatusUpdateResult",
]
