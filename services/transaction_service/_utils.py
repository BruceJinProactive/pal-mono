"""
Transaction Service Utilities

Utility functions for the transaction service.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from agent.tool import ToolMetadata
from db.tables.types import IntegrationProvider, IntegrationType
from utils.log import logger

from .schema import OrderTransactionData


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
    from db.session import SyncSessionLocal

    from ._implementation import create_transaction

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
        transaction = create_transaction(db_session, transaction_data)

        logger.info(
            f"[TransactionService] Saved transaction {transaction.id} "
            f"for {vendor} with external_id {external_transaction_id}"
        )

        return transaction.id

    except Exception as e:
        logger.error(
            f"[TransactionService] Failed to save transaction for {vendor}: {e}",
            exc_info=True,
        )
        return None

    finally:
        if auto_close_session:
            db_session.close()


def update_transaction_by_order_number_helper(
    external_transaction_number: str,
    store_id: str,
    vendor: IntegrationProvider,
    status: Optional[str] = None,
    tracking_link: Optional[str] = None,
    notes: Optional[str] = None,
    session: Optional[Session] = None,
    **kwargs,
) -> bool:
    """
    Helper function to update a transaction by order number with session management.

    This is a convenience function that can be used with asyncio.to_thread() for async contexts.
    It handles session creation and cleanup automatically.

    Args:
        external_transaction_number: The external order number to find
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        status: Transaction status to update
        tracking_link: Tracking link to update
        notes: Notes to update
        session: Optional database session (creates one if not provided)
        **kwargs: Additional fields to update

    Returns:
        bool: True if transaction was found and updated, False otherwise
    """
    from db.session import SyncSessionLocal

    from ._implementation import update_transaction_by_order_number

    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        # Build update fields
        update_fields = {}
        if status is not None:
            update_fields["status"] = status
        if tracking_link is not None:
            update_fields["tracking_link"] = tracking_link
        if notes is not None:
            update_fields["notes"] = notes

        # Add any additional kwargs
        update_fields.update(kwargs)

        if not update_fields:
            logger.warning(
                f"[TransactionService] No fields to update for transaction {external_transaction_number}"
            )
            return False

        # Update the transaction
        transaction = update_transaction_by_order_number(
            session=db_session,
            store_id=store_id,
            vendor=vendor,
            external_transaction_number=external_transaction_number,
            **update_fields,
        )

        if transaction:
            updated_fields = ", ".join(update_fields.keys())
            logger.info(
                f"[TransactionService] Updated transaction {transaction.id} "
                f"for external_transaction_number {external_transaction_number} fields: {updated_fields}"
            )
            return True
        else:
            logger.warning(
                f"[TransactionService] No transaction found with external_transaction_number: {external_transaction_number}, "
                f"vendor: {vendor}, store_id: {store_id}"
            )
            return False

    except Exception as e:
        if auto_close_session:
            db_session.rollback()
        logger.error(
            f"[TransactionService] Error updating transaction {external_transaction_number}: {e}",
            exc_info=True,
        )
        return False

    finally:
        if auto_close_session:
            db_session.close()
