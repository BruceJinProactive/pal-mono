import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
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
                f"[TransactionService] Updated customer_converted for conversation {conversation_id} with order {order_id}"
            )
            return True
        else:
            logger.warning(
                f"[TransactionService] Failed to update customer_converted: conversation {conversation_id} not found"
            )
            return False

    except Exception as e:
        logger.error(
            f"[TransactionService] Error updating customer_converted for conversation {conversation_id}: {e}",
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


async def create_order_from_agent_async(
    session: AsyncSession,
    order_details: Any,
    conversation_id: uuid.UUID,
) -> Optional[Order]:
    """
    Create an order from pal-agents order_details.

    This function handles all type conversions and order creation for orders
    received from the AI agent.

    Args:
        session: Async database session
        order_details: Order details object from pal-agents
        conversation_id: The conversation ID this order belongs to

    Returns:
        Order | None: The created order, or None if creation fails
    """
    try:
        # Convert vendor string to IntegrationProvider enum
        vendor_enum = None
        if order_details.vendor:
            try:
                vendor_enum = IntegrationProvider(order_details.vendor.lower())
            except ValueError:
                logger.warning(
                    f"Invalid vendor value: {order_details.vendor}",
                    extra={"vendor": order_details.vendor},
                )
                return None

        # Convert subtotal to Decimal
        subtotal_decimal = None
        if order_details.subtotal is not None:
            subtotal_decimal = Decimal(str(order_details.subtotal))

        # Convert order_time string to datetime if needed
        order_time_dt = None
        if order_details.order_time:
            if isinstance(order_details.order_time, str):
                try:
                    # Try ISO format first
                    order_time_dt = datetime.fromisoformat(order_details.order_time)
                except ValueError:
                    # Fallback to dateutil parser for more formats
                    from dateutil import parser as dateutil_parser

                    order_time_dt = dateutil_parser.isoparse(order_details.order_time)
            else:
                order_time_dt = order_details.order_time

        # Use run_sync to execute synchronous ORM operations in async context
        def _create_order(sync_session: Session) -> Optional[Order]:
            """Create order in database."""
            order_repo = OrderRepository(sync_session, auto_commit=False)

            # Create new order
            order = order_repo.create_order(
                conversation_id=conversation_id,
                vendor=vendor_enum,
                order_id=order_details.order_id,
                store_id=order_details.store_id,
                user_phone_number=order_details.user_phone_number,
                tracking_link=order_details.tracking_link,
                status=order_details.status,
                fulfillment_strategy=order_details.fulfillment_strategy,
                subtotal=subtotal_decimal,
                order_items=order_details.order_items,
                order_time=order_time_dt,
            )
            return order

        # Execute the order creation
        order = await session.run_sync(_create_order)

        if order:
            await session.commit()
            logger.info(
                "Order persisted to database from agent",
                extra={
                    "conversation_id": str(conversation_id),
                    "order_id": order_details.order_id,
                    "vendor": order_details.vendor,
                    "order_db_id": str(order.id),
                },
            )
        return order

    except Exception as e:
        await session.rollback()
        logger.error(
            "Failed to persist order from agent",
            extra={
                "conversation_id": str(conversation_id),
                "order_id": getattr(order_details, "order_id", None),
                "error": str(e),
            },
        )
        return None


def get_order_by_id(
    session: Session,
    order_id: uuid.UUID,
) -> Optional[Order]:
    """Get an order by its ID."""
    repository = OrderRepository(session, auto_commit=False)
    return repository.get_order_by_id(order_id)


def get_order_by_order_id_store_vendor(
    order_id: str,
    store_id: str,
    vendor: IntegrationProvider,
    session: Optional[Session] = None,
) -> Optional[Order]:
    """
    Get an order by its order ID, store ID, and vendor.

    Args:
        order_id: The order ID to find
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        session: Optional database session (creates one if not provided)

    Returns:
        Order: The order if found, or None if not found
    """
    db_session = session or SyncSessionLocal()
    session_created_here = session is None

    try:
        repository = OrderRepository(db_session, auto_commit=False)
        return repository.get_order_by_order_id_store_vendor(
            order_id=order_id,
            store_id=store_id,
            vendor=vendor,
        )
    finally:
        if session_created_here:
            db_session.close()


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
            f"[TransactionService] Saved order {order.id} "
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
            f"[TransactionService] Failed to save order for {vendor}: {e}",
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
            logger.error("[TransactionService] order_id must be provided")
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
                f"[TransactionService] Updated order {updated_order.id} for order_id {order_id}"
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
            logger.warning(f"[TransactionService] No order found with {criteria}")
            return False

    except Exception as e:
        # Always rollback on exceptions to avoid inconsistent state
        db_session.rollback()
        logger.error(
            f"[TransactionService] Error updating order {order_id}: {e}",
            exc_info=True,
        )
        return False

    finally:
        if session_created_here:
            db_session.close()


def update_order_by_phone(
    store_id: str,
    vendor: IntegrationProvider,
    new_status: str,
    user_phone_number: str,
    order_date: Any,
    tracking_link: Optional[str] = None,
) -> bool:
    """
    Update an order by user phone number and order date.

    This method is specifically designed for updating orders when the order_id
    is not available, using phone number and date for matching instead.

    Args:
        store_id: The store ID to find
        vendor: The integration provider (adora, square, toast, etc.)
        new_status: The new status to set
        user_phone_number: The user's phone number for matching
        order_date: The date of the order for matching (can be date or datetime)
        tracking_link: Optional new tracking link to set

    Returns:
        bool: True if order was found and updated, False otherwise
    """
    db_session = SyncSessionLocal()

    try:
        # Format phone number if needed (add +1 prefix for US numbers)
        formatted_phone = user_phone_number
        if (
            user_phone_number
            and user_phone_number.isdigit()
            and len(user_phone_number) == 10
        ):
            # Raw 10-digit US phone number, add +1 prefix
            formatted_phone = f"+1{user_phone_number}"
        else:
            logger.error(
                f"[TransactionService] Phone number may not be properly formatted: {user_phone_number}"
            )
            raise ValueError("phone number is not formatted")

        if order_date is None:
            raise ValueError("order_date must not be None")
        dt = datetime.strptime(order_date, "%m/%d/%Y %I:%M:%S %p")
        order_date = dt.date()
        start = datetime.combine(order_date, datetime.min.time())

        # Query orders matching the criteria
        query = (
            db_session.query(Order)
            .filter(
                and_(
                    Order.store_id == store_id,
                    Order.status == "pending",
                    Order.vendor == vendor,
                    Order.user_phone_number == formatted_phone,
                    Order.order_time >= start,
                )
            )
            .order_by(Order.created_at.desc())
        )  # Get most recent first

        order = query.first()

        if not order:
            logger.warning(
                f"[TransactionService] No order found with store_id: {store_id}, "
                f"vendor: {vendor}, phone: {formatted_phone} (raw: {user_phone_number}), date: {start}"
            )
            return False

        # Log if there are multiple matching orders
        total_matches = query.count()
        if total_matches > 1:
            logger.warning(
                f"[TransactionService] Found {total_matches} orders matching criteria, "
                f"updating the most recent one (id: {order.id})"
            )

        # Update the order
        order.status = new_status
        if tracking_link is not None:
            order.tracking_link = tracking_link

        order_key = order.id
        order_id = order.order_id
        conversation_id = order.conversation_id

        db_session.commit()

        logger.info(
            f"[TransactionService] Successfully updated order {order_key} "
            f"(order_id: {order_id}) status to {new_status}"
        )

        # If new status is "paid", update customer_converted in conversation
        if new_status and new_status.lower() == "paid":
            _update_customer_converted(
                session=db_session,
                conversation_id=conversation_id,
                order_id=order_key,
            )

        return True

    except Exception as e:
        # Always rollback on exceptions to avoid inconsistent state
        db_session.rollback()
        logger.error(
            f"[TransactionService] Error updating order by phone {user_phone_number}: {e}",
            exc_info=True,
        )
        return False

    finally:
        db_session.close()
