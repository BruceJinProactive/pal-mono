from utils.log import logger

from .schema import ToastWebhookRequest


async def update_menu_content(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the menu content for a given store.

    Args:
        webhook_request: The webhook request containing the menu content
    """
    menu_details = webhook_request.details
    if not menu_details:
        logger.error("No menu details found in webhook request")
        return

    restaurant_guid = menu_details.get("restaurantGuid")
    published_date = menu_details.get("publishedDate")

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
    if not stock_item_details:
        logger.error("No stock item details found in webhook request")
        return

    restaurant_guid = stock_item_details.get("restaurantGuid")
    status = stock_item_details.get("status")
    quantity = stock_item_details.get("quantity")

    logger.debug(
        f"Restaurant {restaurant_guid} updated stock item status to {status} with quantity {quantity}."
        if quantity
        else f"Restaurant {restaurant_guid} updated stock item status to {status}."
    )
