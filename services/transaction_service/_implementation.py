import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from agent.tool import ToolMetadata
from db.repositories import ConversationRepository
from db.repositories.conversation_repository import ConversationUpdate
from db.repositories.order_repository import OrderRepository
from db.session import SyncSessionLocal
from db.tables.orders import Order
from db.tables.types import IntegrationProvider
from utils.log import logger

from ._utils import reconstruct_order_items
from .schema import OrderData


def _update_customer_converted(
    session: Session, conversation_id: uuid.UUID, order_id: uuid.UUID
) -> bool:
    """
    Update the customer_converted field in the conversation with the order ID.

    Args:
        session: Database session
        conversation_id: The conversation ID to update
        order_id: The order ID to set as customer_converted

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        conversation_repo = ConversationRepository(session)
        update_data = ConversationUpdate(customer_converted=order_id)

        updated_conversation = conversation_repo.update_conversation(
            conversation_id=conversation_id,
            update_data=update_data,
        )

        if updated_conversation:
            logger.info(
                f"[OrderService] Updated customer_converted for conversation {conversation_id} with order {order_id}"
            )
            return True
        else:
            logger.warning(
                f"[OrderService] Failed to update customer_converted: conversation {conversation_id} not found"
            )
            return False

    except Exception as e:
        logger.error(
            f"[OrderService] Error updating customer_converted for conversation {conversation_id}: {e}",
            exc_info=True,
        )
        return False


def create_order(
    session: Session,
    order_data: OrderData,
) -> Order:
    """Create a new order record from standardized order data."""
    repository = OrderRepository(session, auto_commit=True)
    return repository.create_order(
        conversation_id=order_data.conversation_id,
        vendor=order_data.vendor,
        order_id=order_data.order_id,
        store_id=order_data.store_id,
        user_phone_number=order_data.user_phone_number,
        store_phone_number=order_data.store_phone_number,
        tracking_link=order_data.tracking_link,
        status=order_data.status,
        fulfillment_strategy=order_data.fulfillment_strategy,
        subtotal=order_data.subtotal,
        order_items=order_data.order_items,
        order_time=order_data.order_time,
    )


def get_order_by_id(
    session: Session,
    order_id: uuid.UUID,
) -> Optional[Order]:
    """Get an order by its ID."""
    repository = OrderRepository(session, auto_commit=False)
    return repository.get_order_by_id(order_id)


def save_order(
    tool_metadata: ToolMetadata,
    vendor: IntegrationProvider,
    order_id: Optional[str] = None,
    store_id: Optional[str] = None,
    status: Optional[str] = "pending",
    fulfillment_strategy: Optional[str] = None,
    subtotal: Optional[Decimal] = None,
    order_items: Optional[List[Any]] = None,
    order_time: Optional[datetime] = None,
    tracking_link: Optional[str] = None,
    session: Optional[Session] = None,
) -> Optional[uuid.UUID]:
    """
    Save an order to the orders table only.

    This is a convenience function for tools to easily save order data
    without having to handle database sessions and order data structures.
    Order items are automatically reconstructed to only include essential fields
    (item_id, item_name, quantity, modifiers) for clean database storage.

    Args:
        tool_metadata: Tool metadata containing session_id
        vendor: The integration provider (adora, square, toast, etc.)
        order_id: Order identifier from the external system
        store_id: Store/location identifier
        status: Order status (default: "pending")
        subtotal: Order subtotal amount
        order_items: List of ordered items (will be reconstructed to essential fields only)
        order_time: When the order occurred (default: now)
        tracking_link: Link to track the order
        session: Optional database session (creates one if not provided)

    Returns:
        uuid.UUID: The ID of the created order, or None if failed
    """
    db_session = session or SyncSessionLocal()
    auto_close_session = session is None

    try:
        # Reconstruct order items to only include essential fields
        reconstructed_order_items = reconstruct_order_items(order_items)

        # Create order data
        order_data = OrderData(
            conversation_id=tool_metadata.session_id,
            vendor=vendor,
            order_id=order_id,
            store_id=store_id,
            user_phone_number=tool_metadata.customer_phone,
            store_phone_number=tool_metadata.store_phone,
            status=status,
            fulfillment_strategy=fulfillment_strategy,
            subtotal=subtotal,
            order_items=reconstructed_order_items or [],
            order_time=order_time or datetime.now(),
            tracking_link=tracking_link,
        )

        # Save the order
        order = create_order(db_session, order_data)

        logger.info(
            f"[OrderService] Saved order {order.id} "
            f"for {vendor} with order_id {order_id}"
        )

        # If order status is "paid", update customer_converted in conversation
        if status and status.lower() == "paid":
            _update_customer_converted(
                session=db_session,
                conversation_id=order.conversation_id,
                order_id=order.id,
            )

        return order.id

    except Exception as e:
        logger.error(
            f"[OrderService] Failed to save order for {vendor}: {e}",
            exc_info=True,
        )
        return None

    finally:
        if auto_close_session:
            db_session.close()


def update_order_by_order_id(
    store_id: str,
    vendor: IntegrationProvider,
    new_status: str,
    order_id: Optional[str] = None,
    tracking_link: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Update an order by its order ID, store ID, vendor, and optional identifiers.

    This helper finds an order using order_id, store_id, vendor, then updates
    its status and tracking link using the OrderRepository for centralized logic.

    Args:
        order_id: The order ID to find
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        new_status: The new status to set
        tracking_link: Optional new tracking link to set
        session: Optional database session (creates one if not provided)

    Returns:
        bool: True if order was found and updated, False otherwise
    """
    db_session = session or SyncSessionLocal()
    session_created_here = session is None

    try:
        if not order_id:
            logger.error("[OrderService] order_id must be provided")
            return False

        # Use OrderRepository for centralized update logic
        repository = OrderRepository(db_session, auto_commit=session_created_here)

        # Build update fields
        update_fields = {"status": new_status}
        if tracking_link is not None:
            update_fields["tracking_link"] = tracking_link

        # Use repository method to update order
        updated_order = repository.update_order_by_order_id(
            store_id=store_id, vendor=vendor, order_id=order_id, **update_fields
        )

        if updated_order:
            logger.debug(
                f"[OrderService] Updated order {updated_order.id} for order_id {order_id}"
            )

            # If new status is "paid", update customer_converted in conversation
            if new_status and new_status.lower() == "paid":
                _update_customer_converted(
                    session=db_session,
                    conversation_id=updated_order.conversation_id,
                    order_id=updated_order.id,
                )

            return True
        else:
            # Build descriptive error message
            criteria = f"order_id: {order_id}, vendor: {vendor}, store_id: {store_id}"
            logger.warning(f"[OrderService] No order found with {criteria}")
            return False

    except Exception as e:
        # Always rollback on exceptions to avoid inconsistent state
        db_session.rollback()
        logger.error(
            f"[OrderService] Error updating order {order_id}: {e}",
            exc_info=True,
        )
        return False

    finally:
        if session_created_here:
            db_session.close()
