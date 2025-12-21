import json
import re

from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from db.session import SyncSessionLocal
from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider
from tools.toast_tool._apis import connect_toast_order_hub
from tools.toast_tool._utils import get_toast_access_token_from_aws
from tools.utils.ordering.classes import HttpMethod
from utils.log import logger

from .schema import (
    ToastPartnerEventType,
    ToastStockItemStatus,
    ToastWebhookMenuDetails,
    ToastWebhookOrderingScheduleDetails,
    ToastWebhookPartnerDetails,
    ToastWebhookRequest,
    ToastWebhookStockItemDetails,
)


def _find_projects_by_restaurant_guid(
    restaurant_guid: str, session: Session
) -> list[Project]:
    """
    Find projects using ProjectIntegration table with Toast provider verification.
    Uses pure ORM approach for robustness and early filtering.

    Flow: restaurant_guid → ProjectIntegration(store_identifier + provider=toast) → Project

    Args:
        restaurant_guid: The Toast restaurant GUID
        session: Database session

    Returns:
        List of Project objects or empty list if none found
    """
    try:

        toast_projects = (
            session.query(Project)
            .join(ProjectIntegration, Project.id == ProjectIntegration.project_id)
            .join(Integration, ProjectIntegration.integration_id == Integration.id)
            .filter(
                ProjectIntegration.store_identifier == restaurant_guid,
                Integration.provider == IntegrationProvider.toast,
            )
            .distinct()
            .all()
        )

        if not toast_projects:
            logger.warning(
                f"[ToastWebhook._find_projects_by_restaurant_guid] No Toast projects found with store_identifier: {restaurant_guid}"
            )
            return []
        # Add warning if multiple projects are found
        if len(toast_projects) > 1:
            logger.warning(
                f"[ToastWebhook._find_projects_by_restaurant_guid] Multiple Toast projects found with store_identifier: {restaurant_guid}"
            )
        else:
            logger.debug(
                f"[ToastWebhook._find_projects_by_restaurant_guid] Found {len(toast_projects)} Toast projects for restaurant_guid: {restaurant_guid}"
            )

        for project in toast_projects:
            logger.debug(
                f"[ToastWebhook._find_projects_by_restaurant_guid] Found Toast project {project.name} (ID: {project.id}) for restaurant_guid: {restaurant_guid}"
            )

        return toast_projects

    except Exception as e:
        logger.error(
            f"[ToastWebhook._find_projects_by_restaurant_guid] Error finding projects via ProjectIntegration for restaurant_guid {restaurant_guid}: {e}"
        )
        return []


def _update_stock_section(
    content: str,
    item_name: str,
    item_guid: str,
    stock_message: str | None = None,
) -> str:
    """
    Update or remove an item in the OUT-OF-STOCK section.

    Args:
        content: The content to update
        item_name: Name of the menu item
        item_guid: Toast item GUID
        stock_message: Stock message to add/update (None to remove item)

    Returns:
        Updated content with stock section modified
    """
    start_header = "### OUT-OF-STOCK ###"
    end_header = "### OUT-OF-STOCK-ENDS ###"

    # If no stock section exists and we're removing, return unchanged
    if stock_message is None and start_header not in content:
        return content

    # If no stock section exists and we're adding, create new section
    if stock_message is not None and start_header not in content:
        return content + f"\n\n{start_header}\n{stock_message}\n{end_header}\n"

    # Find section boundaries
    section_start = content.find(start_header) + len(start_header)
    end_marker_pos = content.find(end_header, section_start)

    if end_marker_pos != -1:
        section_end = end_marker_pos
        has_end_marker = True
        full_section_end = end_marker_pos + len(end_header)
    else:
        # Fallback to legacy layouts (no explicit end marker): find the next header
        # Works for both LF and CRLF by dropping on start-of-line "###".
        next_header_match = re.search(r"^###\s+", content[section_start:], re.MULTILINE)
        if next_header_match:
            section_end = section_start + next_header_match.start()
        else:
            section_end = len(content)
        has_end_marker = False
        full_section_end = section_end

    # Extract current section content
    section = content[section_start:section_end]
    # Pattern matches both old format (with ID) and new format (without ID)
    # Old: "- Item Name (ID: guid) is OUT OF STOCK..."
    # New: "- Item Name is OUT OF STOCK..."
    item_pattern = (
        rf"- {re.escape(item_name)}(?: \(ID: {re.escape(item_guid)}\))?.*?(\r?\n|$)"
    )

    if stock_message is not None:
        # Adding or updating item
        if re.search(item_pattern, section):
            # Item exists, update it
            new_section = re.sub(item_pattern, f"{stock_message}\n", section)
        else:
            # Item doesn't exist, add it
            new_section = f"\n{stock_message}" + section

        # Ensure end marker is present
        if has_end_marker:
            return content[:section_start] + new_section + content[section_end:]
        else:
            return (
                content[:section_start]
                + new_section
                + f"\n{end_header}"
                + content[section_end:]
            )

    else:
        # Removing item
        new_section = re.sub(item_pattern, "", section)

        # If section is now empty, remove entire section
        if re.search(r"^\s*(\r?\n)*$", new_section):
            before_header = content[: content.find(start_header)]
            after_section = content[full_section_end:]
            # Clean up extra newlines
            if before_header.endswith("\n\n") and after_section.startswith("\n"):
                after_section = after_section[1:]
            return before_header.rstrip() + after_section
        else:
            # Keep section but ensure end marker is present
            if has_end_marker:
                return content[:section_start] + new_section + content[section_end:]
            else:
                return (
                    content[:section_start]
                    + new_section
                    + f"\n{end_header}"
                    + content[section_end:]
                )


def _get_item_name_from_toast_api(item_guid: str, restaurant_guid: str) -> str:
    """
    Retrieve item name from Toast Config API using item GUID.

    Args:
        item_guid: Toast item GUID
        restaurant_guid: Toast restaurant GUID

    Returns:
        Item name from Toast API or fallback name
    """
    try:
        # Get Toast access token from AWS
        bearer_token = get_toast_access_token_from_aws()

        # Call Toast Config API to get menu item details
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function=f"/config/v2/menuItems/{item_guid}",
            store_id=restaurant_guid,
            query_params=None,
            payload=None,
        )

        if response.status == 200:
            # Parse the response to get the item name
            item_data = json.loads(response.decoded_body)
            item_name = item_data.get("name", f"Toast Item {item_guid}")
            logger.debug(
                f"[ToastWebhook._get_item_name_from_toast_api] Found item name from Toast API: {item_name} for itemGuid: {item_guid}"
            )
            return item_name
        else:
            logger.warning(
                f"[ToastWebhook._get_item_name_from_toast_api] Failed to get item from Toast API (status {response.status}): {response.decoded_body}"
            )
            return f"Toast Item {item_guid}"

    except Exception as e:
        logger.warning(
            f"[ToastWebhook._get_item_name_from_toast_api] Could not retrieve item from Toast API: {e}"
        )
        return f"Toast Item {item_guid}"


def _update_stock_in_project_product_info(
    projects: list[Project],
    item_name: str,
    item_guid: str,
    status: ToastStockItemStatus,
    session: Session,
) -> None:
    """
    Update stock information in project product_info field.

    Args:
        projects: List of projects to update
        item_name: Name of the menu item
        item_guid: Toast item GUID
        status: Stock status
        session: Database session
    """
    try:
        for project in projects:
            # Lock the row to avoid lost updates when multiple webhooks touch the same project concurrently
            locked = (
                session.query(Project)
                .filter(Project.id == project.id)
                .with_for_update(nowait=False)
                .one()
            )

            current_content = locked.product_info or ""

            if status == ToastStockItemStatus.OUT_OF_STOCK:
                stock_message = f"- {item_name} is OUT OF STOCK. You MUST NOT accept orders for this item under any circumstances."
                new_content = _update_stock_section(
                    current_content, item_name, item_guid, stock_message
                )
            else:
                # Item is back in stock - remove from out of stock list
                new_content = _update_stock_section(
                    current_content, item_name, item_guid, None
                )

            # Update the project if content changed
            if new_content != current_content:
                locked.product_info = new_content
                session.add(locked)
                logger.debug(
                    f"[ToastWebhook._update_stock_in_project_product_info] Updated stock status in project '{project.name}' product_info for item {item_name}"
                )

        # Commit all changes
        session.commit()
        logger.debug(
            f"[ToastWebhook._update_stock_in_project_product_info] Successfully updated stock information for {item_name} in {len(projects)} projects"
        )

    except Exception as e:
        session.rollback()
        logger.error(
            f"[ToastWebhook._update_stock_in_project_product_info] Error updating stock information in project product_info: {e}"
        )
        raise


# Legacy functions removed - keeping only the above clean approach


async def update_menu_content(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the menu content for a given store.

    Args:
        webhook_request: The webhook request containing the menu content
    """
    try:
        menu_details = ToastWebhookMenuDetails(**webhook_request.details)
    except ValidationError as e:
        logger.error("[ToastWebhook.update_menu_content] Invalid menu details: %s", e)
        return

    restaurant_guid = menu_details.restaurantGuid
    published_date = menu_details.publishedDate

    logger.debug(
        f"[ToastWebhook.update_menu_content] Restaurant {restaurant_guid} updated menu content at {published_date}. "
        "Updating menu content in database."
    )


def _process_stock_item_status_sync(webhook_request: ToastWebhookRequest) -> None:
    """
    Synchronous helper function to process stock item status updates.
    This function contains all the blocking DB and Toast API operations.
    """
    try:
        stock_item_details = ToastWebhookStockItemDetails(**webhook_request.details)
    except ValidationError as e:
        logger.error(
            "[ToastWebhook._process_stock_item_status_sync] Invalid stock item details: %s",
            e,
        )
        return

    restaurant_guid = stock_item_details.restaurantGuid
    item_guid = stock_item_details.itemGuid
    status = stock_item_details.status
    quantity = stock_item_details.quantity

    logger.debug(
        f"[ToastWebhook._process_stock_item_status_sync] Restaurant {restaurant_guid} updated stock item {item_guid} status to {status} with quantity {quantity}."
        if quantity
        else f"[ToastWebhook._process_stock_item_status_sync] Restaurant {restaurant_guid} updated stock item {item_guid} status to {status}."
    )

    with SyncSessionLocal() as session:
        try:
            # Find the projects associated with this restaurant using ProjectIntegration table
            projects = _find_projects_by_restaurant_guid(restaurant_guid, session)

            if not projects:
                logger.debug(
                    "[ToastWebhook._process_stock_item_status_sync] No projects configured, skipping",
                    extra={"restaurant_guid": restaurant_guid},
                )
                return

            # Get item name from Toast Config API
            item_name = f"Toast Item {item_guid}"  # fallback

            try:
                item_name = _get_item_name_from_toast_api(item_guid, restaurant_guid)
            except Exception as e:
                logger.warning(
                    f"[ToastWebhook._process_stock_item_status_sync] Error retrieving item name from Toast API, using fallback: {e}"
                )

            logger.debug(
                f"[ToastWebhook._process_stock_item_status_sync] Updating stock status for item '{item_name}' to {status.value} in {len(projects)} projects"
            )

            # Update the stock item status in project product_info fields
            _update_stock_in_project_product_info(
                projects, item_name, item_guid, status, session
            )

            # Log completion
            logger.debug(
                f"[ToastWebhook._process_stock_item_status_sync] Successfully processed stock update for restaurant {restaurant_guid}, "
                f"item '{item_name}' ({item_guid}), status: {status.value} across {len(projects)} projects"
            )

        except Exception as e:
            session.rollback()
            logger.error(
                f"[ToastWebhook._process_stock_item_status_sync] Error processing stock item status update: {e}"
            )
            raise


async def update_stock_item_status(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the stock item status for a given store.

    Args:
        webhook_request: The webhook request containing the stock item status
    """
    # Offload blocking work
    await run_in_threadpool(_process_stock_item_status_sync, webhook_request)


def _format_time_12h(hour: int, minute: int) -> str:
    """
    Convert 24-hour time to 12-hour AM/PM format.

    Args:
        hour: Hour (0-23)
        minute: Minute (0-59)

    Returns:
        Formatted time string (e.g., "11 AM", "8:30 PM")
    """
    period = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    display_hour = 12 if display_hour == 0 else display_hour

    if minute == 0:
        return f"{display_hour} {period}"
    return f"{display_hour}:{minute:02d} {period}"


def _group_consecutive_days(day_schedules: dict[str, str]) -> list[str]:
    """
    Group consecutive days with the same hours together.

    Args:
        day_schedules: Map of day name to time range string

    Returns:
        List of formatted day/time strings
    """
    day_order = [
        "MONDAY",
        "TUESDAY",
        "WEDNESDAY",
        "THURSDAY",
        "FRIDAY",
        "SATURDAY",
        "SUNDAY",
    ]
    grouped = []

    # Group days by their time ranges
    time_to_days: dict[str, list[str]] = {}
    for day in day_order:
        if day in day_schedules:
            time_str = day_schedules[day]
            if time_str not in time_to_days:
                time_to_days[time_str] = []
            time_to_days[time_str].append(day)

    # Format grouped days
    for time_str, days in time_to_days.items():
        if len(days) == 1:
            day_label = days[0].capitalize()
        else:
            # Check if consecutive
            indices = [day_order.index(d) for d in days]
            if indices == list(range(min(indices), max(indices) + 1)):
                # Consecutive days
                day_label = f"{days[0].capitalize()}-{days[-1].capitalize()}"
            else:
                # Non-consecutive, list them
                day_label = ", ".join(d.capitalize() for d in days)

        grouped.append(f"{day_label}: {time_str}")

    return grouped


def _format_ordering_schedule(
    service_periods: list,
    overrides: list,
) -> str:
    """
    Format ordering schedule into human-readable text.

    Args:
        service_periods: List of ServicePeriod objects
        overrides: List of Override objects

    Returns:
        Formatted schedule string
        Example:
            "
            Delivery:
            Monday-Thursday: 11 AM-8 PM
            Friday: 11 AM-9 PM
            Saturday-Sunday: 11 AM-9 PM

            Take Out:
            Monday-Thursday: 11 AM-8 PM
            Friday: 11 AM-9 PM, 2 PM-5 PM
            Saturday-Sunday: 10 AM-9 PM

            Special Events:

            Thanksgiving Day - Thursday, November 27, 2025
              Delivery, Take Out: 9:30 AM-3 PM

            Christmas - Wednesday, December 25, 2025
              Delivery, Take Out: CLOSED
            "
    """
    from datetime import date, datetime

    result = []

    # Process service periods by dining option
    dining_options: dict[str, dict[str, str]] = {}
    for period in service_periods:
        option = period.diningOptionBehavior.replace("_", " ").title()
        day_schedules: dict[str, str] = {}

        for day_period in period.dayPeriods:
            day = day_period.day
            time_ranges = []

            for tr in day_period.timeRanges:
                start_h, start_m = tr.start[0], tr.start[1]
                end_h, end_m = tr.end[0], tr.end[1]
                start_str = _format_time_12h(start_h, start_m)
                end_str = _format_time_12h(end_h, end_m)
                time_ranges.append(f"{start_str}-{end_str}")

            if time_ranges:
                day_schedules[day] = ", ".join(time_ranges)

        dining_options[option] = day_schedules

    # Format regular schedule
    for option, schedules in dining_options.items():
        result.append(f"\n{option}:")
        grouped = _group_consecutive_days(schedules)
        for line in grouped:
            result.append(f"{line}")

    # Process overrides (special events)
    today = date.today()
    future_overrides = []

    for override in overrides:
        # Parse business date from YYYYMMDD format
        date_str = str(override.businessDate)
        event_date = datetime.strptime(date_str, "%Y%m%d").date()

        if event_date >= today:
            # Format time ranges
            if not override.timeRanges:
                hours = "CLOSED"
            else:
                time_strs = []
                for tr in override.timeRanges:
                    start_h, start_m = tr.start[0], tr.start[1]
                    end_h, end_m = tr.end[0], tr.end[1]
                    start_str = _format_time_12h(start_h, start_m)
                    end_str = _format_time_12h(end_h, end_m)
                    time_strs.append(f"{start_str}-{end_str}")
                hours = ", ".join(time_strs)

            # Format dining options
            options = ", ".join(
                opt.replace("_", " ").title() for opt in override.diningOptionBehavior
            )

            future_overrides.append(
                {
                    "date": event_date,
                    "name": override.description,
                    "hours": hours,
                    "options": options,
                }
            )

    # Add special events section
    if future_overrides:
        result.append("\n\nSpecial Events:")
        # Sort by date
        future_overrides.sort(key=lambda x: x["date"])

        for event in future_overrides:
            date_str = event["date"].strftime("%A, %B %d, %Y")
            result.append(f"\n{event['name']} - {date_str}")
            result.append(f"  {event['options']}: {event['hours']}")

    return "\n".join(result)


def _store_ordering_schedule_in_db(
    restaurant_guid: str,
    formatted_schedule: str,
) -> None:
    """
    Store formatted ordering schedule in project store_hours field.

    Args:
        restaurant_guid: Toast restaurant GUID
        formatted_schedule: Formatted schedule string
    """
    with SyncSessionLocal() as session:
        try:
            # Find projects
            projects = _find_projects_by_restaurant_guid(restaurant_guid, session)

            if not projects:
                logger.warning(
                    f"[ToastWebhook._store_ordering_schedule_in_db] No projects found for restaurant {restaurant_guid}"
                )
                return

            # Update each project
            for project in projects:
                locked = (
                    session.query(Project)
                    .filter(Project.id == project.id)
                    .with_for_update(nowait=False)
                    .one()
                )

                locked.store_hours = formatted_schedule
                session.add(locked)

                logger.debug(
                    f"[ToastWebhook._store_ordering_schedule_in_db] Updated ordering schedule for project '{project.name}'"
                )

            session.commit()
            logger.debug(
                f"[ToastWebhook._store_ordering_schedule_in_db] Successfully updated ordering schedule for {len(projects)} projects"
            )

        except Exception as e:
            session.rollback()
            logger.error(
                f"[ToastWebhook._store_ordering_schedule_in_db] Error storing schedule: {e}"
            )
            raise


async def update_ordering_schedule(webhook_request: ToastWebhookRequest) -> None:
    """
    Update the ordering schedule for a given store.

    Args:
        webhook_request: The webhook request containing the ordering schedule
    """
    try:
        ordering_schedule_details = ToastWebhookOrderingScheduleDetails(
            **webhook_request.details
        )
    except ValidationError as e:
        logger.error(
            "[ToastWebhook.update_ordering_schedule] Invalid ordering schedule details: %s",
            e,
        )
        return

    restaurant_guid = ordering_schedule_details.restaurantGuid
    ordering_schedule = ordering_schedule_details.orderingSchedule

    logger.debug(
        f"[ToastWebhook.update_ordering_schedule] Restaurant {restaurant_guid} updating ordering schedule"
    )

    # Format the schedule into human-readable text
    formatted_schedule = _format_ordering_schedule(
        ordering_schedule.servicePeriods,
        ordering_schedule.overrides,
    )

    logger.debug(
        f"[ToastWebhook.update_ordering_schedule] Formatted schedule:\n{formatted_schedule}"
    )

    # Store in database (run in threadpool to avoid blocking)
    await run_in_threadpool(
        _store_ordering_schedule_in_db,
        restaurant_guid,
        formatted_schedule,
    )


def _process_partner_added_event(partner_details: ToastWebhookPartnerDetails) -> None:
    """
    Process partner_added event - when integration is added to a restaurant.

    Args:
        partner_details: The partner event details
    """
    restaurant_guid = partner_details.restaurantGuid
    restaurant_name = partner_details.restaurantName
    location_name = partner_details.locationName or "N/A"

    logger.debug(
        f"[ToastWebhook._process_partner_added_event] Integration added to restaurant: "
        f"{restaurant_name} ({location_name}) - GUID: {restaurant_guid}"
    )

    # Log important details
    if partner_details.managementGroupGuid:
        logger.debug(
            f"[ToastWebhook._process_partner_added_event] Restaurant belongs to management group: {partner_details.managementGroupGuid}"
        )

    if partner_details.externalGroupRef or partner_details.externalRestaurantRef:
        logger.debug(
            f"[ToastWebhook._process_partner_added_event] External references - Group: {partner_details.externalGroupRef}, Restaurant: {partner_details.externalRestaurantRef}"
        )

    # Add business logic here in the future, such as:
    # - Creating/updating project integrations in the database
    # - Sending notifications to admin users
    # - Triggering menu sync processes
    # - Setting up initial configuration


def _process_partner_removed_event(partner_details: ToastWebhookPartnerDetails) -> None:
    """
    Process partner_removed event - when integration is removed from a restaurant.

    Args:
        partner_details: The partner event details
    """
    restaurant_guid = partner_details.restaurantGuid
    restaurant_name = partner_details.restaurantName
    location_name = partner_details.locationName or "N/A"

    logger.debug(
        f"[ToastWebhook._process_partner_removed_event] Integration removed from restaurant: "
        f"{restaurant_name} ({location_name}) - GUID: {restaurant_guid}"
    )

    # Add business logic here in the future, such as:
    # - Removing/deactivating project integrations in the database
    # - Cleaning up associated data
    # - Sending notifications to admin users
    # - Stopping any scheduled sync processes


def _process_partner_updated_event(partner_details: ToastWebhookPartnerDetails) -> None:
    """
    Process partner_updated event - when integration settings are updated.

    Args:
        partner_details: The partner event details
    """
    restaurant_guid = partner_details.restaurantGuid
    restaurant_name = partner_details.restaurantName
    location_name = partner_details.locationName or "N/A"

    logger.debug(
        f"[ToastWebhook._process_partner_updated_event] Integration settings updated for restaurant: "
        f"{restaurant_name} ({location_name}) - GUID: {restaurant_guid}"
    )

    # Log what might have changed
    logger.debug(
        f"[ToastWebhook._process_partner_updated_event] Current external references - Group: {partner_details.externalGroupRef}, Restaurant: {partner_details.externalRestaurantRef}"
    )

    # Add business logic here in the future, such as:
    # - Updating project integration settings in the database
    # - Validating external reference changes
    # - Sending notifications about configuration changes
    # - Re-syncing menu data if necessary


async def process_partner_event(webhook_request: ToastWebhookRequest) -> None:
    """
    Process partner webhook events (partner_added, partner_removed, partner_updated).

    Args:
        webhook_request: The webhook request containing the partner event details
    """
    try:
        partner_details = ToastWebhookPartnerDetails(**webhook_request.details)
    except ValidationError as e:
        logger.error(
            "[ToastWebhook.process_partner_event] Invalid partner event details: %s", e
        )
        return

    raw_event_type = webhook_request.eventType
    try:
        event_type = ToastPartnerEventType(raw_event_type)
    except ValueError:
        logger.warning(
            f"[ToastWebhook.process_partner_event] Unknown partner event type: {raw_event_type}"
        )
        return

    logger.debug(
        f"[ToastWebhook.process_partner_event] Processing partner event: {event_type} "
        f"for restaurant {partner_details.restaurantName} (GUID: {partner_details.restaurantGuid})"
    )

    # Process the event based on type
    try:
        match event_type:
            case ToastPartnerEventType.PARTNER_ADDED:
                _process_partner_added_event(partner_details)
            case ToastPartnerEventType.PARTNER_REMOVED:
                _process_partner_removed_event(partner_details)
            case ToastPartnerEventType.PARTNER_UPDATED:
                _process_partner_updated_event(partner_details)

        logger.debug(
            f"[ToastWebhook.process_partner_event] Successfully processed partner event: {event_type} "
            f"for restaurant GUID: {partner_details.restaurantGuid}"
        )

    except Exception as e:
        logger.error(
            f"[ToastWebhook.process_partner_event] Error processing partner event {event_type}: {e}"
        )
        raise
