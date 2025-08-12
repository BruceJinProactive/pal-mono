"""
Transaction Helper Utilities

Shared utilities for tools to easily save transaction data to the database.
This module provides convenience functions that abstract away the complexity
of creating and managing transaction records across different integration providers.

"""

__all__ = [
    "save_transaction",
    "update_transaction_status_helper",
    "update_tracking_link_helper",
    "update_transaction_by_order_number",
    "reconstruct_order_items",
]

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from agent.tool import ToolMetadata
from db.session import SyncSessionLocal
from db.tables.types import IntegrationProvider, IntegrationType
from services.transaction_service import (
    OrderTransactionData,
    create_transaction,
    update_transaction_status,
    update_transaction_tracking_link,
)
from utils.log import logger


def reconstruct_order_items(order_items: Optional[List[Any]]) -> Optional[List[dict]]:
    """Extract essential fields from order items for clean database storage."""
    if not order_items:
        return None

    def get_field(obj, *field_names):
        """Get first available field from object or dict-like."""
        for field in field_names:
            if isinstance(obj, dict) and field in obj:
                return obj.get(field)
            if hasattr(obj, field):
                return getattr(obj, field)
        return None

    def extract_modifiers(modifiers):
        """Extract essential modifier fields."""
        if not modifiers:
            return None
        return [
            {
                "modifier_id": get_field(mod, "modifier_id", "id"),
                "modifier_name": get_field(mod, "modifier_name", "name"),
            }
            for mod in modifiers
            if get_field(mod, "modifier_id", "id")
        ]

    result = []
    for item in order_items:
        item_id = get_field(item, "item_id", "id")
        if not item_id:
            continue

        quantity = get_field(item, "quantity", "qty")
        if quantity is None:
            quantity = 1

        reconstructed = {
            "item_id": item_id,
            "item_name": get_field(item, "item_name", "name"),
            "quantity": quantity,
        }

        modifiers = extract_modifiers(get_field(item, "modifiers", "mods"))
        if modifiers:
            reconstructed["modifiers"] = modifiers

        result.append(reconstructed)

    return result if result else None


def save_transaction(
    tool_metadata: ToolMetadata,
    vendor: IntegrationProvider,
    external_transaction_id: str,
    external_transaction_number: Optional[str] = None,
    store_id: Optional[str] = None,
    status: Optional[str] = "pending",
    integration_type: Optional[IntegrationType] = None,
    fulfillment_strategy: Optional[str] = None,
    subtotal: Optional[Decimal] = None,
    order_items: Optional[List[Any]] = None,
    order_time: Optional[datetime] = None,
    tracking_link: Optional[str] = None,
    notes: Optional[str] = None,
    session: Optional[Session] = None,
) -> Optional[uuid.UUID]:
    """
    Save a transaction to the transactions table only.

    This is a convenience function for tools to easily save transaction data
    without having to handle database sessions and transaction data structures.
    Order items are automatically reconstructed to only include essential fields
    (item_id, item_name, quantity, modifiers) for clean database storage.

    Args:
        tool_metadata: Tool metadata containing session_id, user_id, project_id
        vendor: The integration provider (adora, square, toast, etc.)
        external_transaction_id: The transaction ID from the external system
        external_transaction_number: Human-readable transaction number
        store_id: Store/location identifier
        status: Transaction status (default: "pending")
        subtotal: Transaction subtotal amount
        order_items: List of ordered items (will be reconstructed to essential fields only)
        order_time: When the transaction occurred (default: now)
        tracking_link: Link to track the transaction
        notes: Additional notes
        session: Optional database session (creates one if not provided)

    Returns:
        uuid.UUID: The ID of the created transaction, or None if failed
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        # Build notes with customer phone if provided
        transaction_notes = notes or ""

        # Reconstruct order items to only include essential fields
        reconstructed_order_items = reconstruct_order_items(order_items)

        # Create transaction data
        transaction_data = OrderTransactionData(
            external_transaction_id=external_transaction_id,
            external_transaction_number=external_transaction_number,
            conversation_id=tool_metadata.session_id,
            user_id=tool_metadata.user_id,
            project_id=tool_metadata.project_id,
            vendor=vendor,
            store_id=store_id,
            status=status,
            integration_type=integration_type,
            fulfillment_strategy=fulfillment_strategy,
            subtotal=subtotal,
            order_items=reconstructed_order_items or [],
            order_time=order_time or datetime.now(),
            tracking_link=tracking_link,
            notes=transaction_notes or None,
        )

        # Save the transaction
        transaction = create_transaction(db_session, transaction_data, auto_commit=True)

        logger.info(
            f"[TransactionHelper] Saved transaction {transaction.id} "
            f"for {vendor} with external_id {external_transaction_id}"
        )

        return transaction.id

    except Exception as e:
        logger.error(
            f"[TransactionHelper] Failed to save transaction for {vendor}: {e}",
            exc_info=True,
        )
        return None

    finally:
        if auto_close_session:
            db_session.close()


def update_transaction_status_helper(
    transaction_id: uuid.UUID,
    status: str,
    session: Optional[Session] = None,
) -> bool:
    """
    Update the status of a transaction.

    Args:
        transaction_id: The ID of the transaction to update
        status: The new status
        session: Optional database session (creates one if not provided)

    Returns:
        bool: True if successful, False otherwise
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        result = update_transaction_status(
            db_session, transaction_id, status, auto_commit=True
        )
        success = result is not None

        if success:
            logger.info(
                f"[TransactionHelper] Updated transaction {transaction_id} status to {status}"
            )
        else:
            logger.warning(
                f"[TransactionHelper] Failed to update transaction {transaction_id} - not found"
            )

        return success

    except Exception as e:
        logger.error(
            f"[TransactionHelper] Failed to update transaction {transaction_id} status: {e}",
            exc_info=True,
        )
        return False

    finally:
        if auto_close_session:
            db_session.close()


def update_tracking_link_helper(
    transaction_id: uuid.UUID,
    tracking_link: str,
    session: Optional[Session] = None,
) -> bool:
    """
    Update the tracking link of a transaction.

    Args:
        transaction_id: The ID of the transaction to update
        tracking_link: The new tracking link
        session: Optional database session (creates one if not provided)

    Returns:
        bool: True if successful, False otherwise
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        result = update_transaction_tracking_link(
            db_session, transaction_id, tracking_link, auto_commit=True
        )
        success = result is not None

        if success:
            logger.info(
                f"[TransactionHelper] Updated transaction {transaction_id} tracking link"
            )
        else:
            logger.warning(
                f"[TransactionHelper] Failed to update transaction {transaction_id} - not found"
            )

        return success

    except Exception as e:
        logger.error(
            f"[TransactionHelper] Failed to update transaction {transaction_id} tracking link: {e}",
            exc_info=True,
        )
        return False

    finally:
        if auto_close_session:
            db_session.close()


def update_transaction_by_order_number(
    store_id: str,
    vendor: IntegrationProvider,
    new_status: str,
    external_transaction_number: Optional[str] = None,
    tracking_link: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Update a transaction by its external transaction ID, store ID, vendor, and optional identifiers.

    This helper finds a transaction using external_transaction_number, store_id, vendor, and optionally
    transaction_number, then updates its status and tracking link.

    Args:
        external_transaction_number: The external ordernumber to find
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        new_status: The new status to set
        tracking_link: Optional new tracking link to set
        session: Optional database session (creates one if not provided)

    Returns:
        bool: True if transaction was found and updated, False otherwise
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        # Import here to avoid circular imports
        from db.tables.transactions import Transaction

        if not external_transaction_number:
            logger.error(
                "[TransactionHelper] external_transaction_number must be provided"
            )
            return False

        # Build query filters
        filters = [
            Transaction.external_transaction_number == external_transaction_number,
            Transaction.vendor == vendor,
            Transaction.store_id == store_id,
        ]

        # Find the transaction with all specified criteria
        transaction = db_session.query(Transaction).filter(*filters).first()

        if transaction:
            # Update transaction status and tracking link
            transaction.status = new_status
            if tracking_link is not None:
                transaction.tracking_link = tracking_link
            transaction.order_time = datetime.now()
            if auto_close_session:
                db_session.commit()

            logger.debug(
                f"[TransactionHelper] Updated transaction {transaction.id} for external_transaction_number {external_transaction_number}"
            )
            return True
        else:
            # Build descriptive error message
            criteria = f"external_transaction_number: {external_transaction_number}, vendor: {vendor}, store_id: {store_id}"
            if external_transaction_number:
                criteria += (
                    f", external_transaction_number: {external_transaction_number}"
                )

            logger.warning(f"[TransactionHelper] No transaction found with {criteria}")
            return False

    except Exception as e:
        if auto_close_session:
            db_session.rollback()
        logger.error(
            f"[TransactionHelper] Error updating transaction {external_transaction_number}: {e}",
            exc_info=True,
        )
        return False

    finally:
        if auto_close_session:
            db_session.close()
