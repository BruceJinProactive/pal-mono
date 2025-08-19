from utils.log import logger

from .schema import (
    ToastWebhookMenuDetails,
    ToastWebhookOrderingScheduleDetails,
    ToastWebhookRequest,
    ToastWebhookStockItemDetails,
)


async def update_menu_content(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the menu content for a given store.

    Args:
        webhook_request: The webhook request containing the menu content
    """
    menu_details = webhook_request.details
    menu_details = ToastWebhookMenuDetails(**menu_details)
    if not menu_details:
        logger.error("No menu details found in webhook request")
        return

    restaurant_guid = menu_details.restaurantGuid
    published_date = menu_details.publishedDate

    logger.debug(
        f"Restaurant {restaurant_guid} updated menu content at {published_date}. "
        "Updating menu content in database."
    )


async def update_stock_item_status(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the stock item status for a given store.

    Args:
        webhook_request: The webhook request containing the stock item status
    """
    stock_item_details = webhook_request.details
    stock_item_details = ToastWebhookStockItemDetails(**stock_item_details)
    if not stock_item_details:
        logger.error("No stock item details found in webhook request")
        return

    restaurant_guid = stock_item_details.restaurantGuid
    status = stock_item_details.status
    quantity = stock_item_details.quantity

    logger.debug(
        f"Restaurant {restaurant_guid} updated stock item status to {status} with quantity {quantity}."
        if quantity
        else f"Restaurant {restaurant_guid} updated stock item status to {status}."
    )


async def update_ordering_schedule(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the ordering schedule for a given store.

    Args:
        webhook_request: The webhook request containing the ordering schedule
    """
    ordering_schedule_details = webhook_request.details
    ordering_schedule_details = ToastWebhookOrderingScheduleDetails(
        **ordering_schedule_details
    )
    if not ordering_schedule_details:
        logger.error("No ordering schedule details found in webhook request")
        return

    restaurant_guid = ordering_schedule_details.restaurantGuid
    ordering_schedule = ordering_schedule_details.orderingSchedule
    scheduled_order_max_days = ordering_schedule.scheduledOrderMaxDays
    last_order_configuration = ordering_schedule.lastOrderConfiguration

    logger.debug(
        f"Restaurant {restaurant_guid} updated ordering schedule to {ordering_schedule}. "
        f"Scheduled order max days: {scheduled_order_max_days}. "
        f"Last order configuration: {last_order_configuration}."
    )
