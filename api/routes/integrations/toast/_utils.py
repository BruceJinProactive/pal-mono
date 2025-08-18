from utils.log import logger

from .schema import ToastWebhookRequest


async def update_menu_content(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the menu content for a given store.

    Args:
        webhook_request: The webhook request containing the menu content
    """
    menu_details = webhook_request.details.get("menuDetails")
    if not menu_details:
        logger.error("No menu details found in webhook request")
        return

    restaurant_guid = menu_details.get("restaurantGuid")
    published_date = menu_details.get("publishedDate")

    logger.debug(
        f"Restaurant {restaurant_guid} updated menu content at {published_date}. "
        "Updating menu content in database."
    )
