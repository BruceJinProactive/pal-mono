import json
import re
from datetime import datetime
from typing import Any

from pal_agents.menu_assets.toast import (
    build_toast_lookup_prompt_context_markdown,
    compile_toast_menu_v2,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from db.repositories.project_integration_repository import ProjectIntegrationRepository
from db.repositories.project_repository import ProjectRepository
from db.session import SyncSessionLocal
from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider
from services.knowledge_service.toast._client import download_menu
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

        return toast_projects

    except Exception as e:
        logger.error(
            f"[ToastWebhook._find_projects_by_restaurant_guid] Error finding projects via ProjectIntegration for restaurant_guid {restaurant_guid}: {e}"
        )
        return []


def _find_toast_project_integrations_by_restaurant_guid(
    restaurant_guid: str, session: Session
) -> list[tuple[Project, ProjectIntegration]]:
    """Find Toast project integrations for a restaurant GUID."""
    project_integration_repository = ProjectIntegrationRepository(
        session, auto_commit=False
    )
    project_repository = ProjectRepository(session, auto_commit=False)

    project_integrations = project_integration_repository.get_project_integrations_by_store_identifier_and_provider(
        restaurant_guid,
        IntegrationProvider.toast,
    )
    if not project_integrations:
        logger.warning(
            "[ToastWebhook._find_toast_project_integrations_by_restaurant_guid] "
            "No Toast project integrations found with store_identifier: %s",
            restaurant_guid,
        )
        return []

    if len(project_integrations) > 1:
        logger.warning(
            "[ToastWebhook._find_toast_project_integrations_by_restaurant_guid] "
            "Multiple Toast project integrations found with store_identifier: %s",
            restaurant_guid,
        )

    project_pairs: list[tuple[Project, ProjectIntegration]] = []
    for project_integration in project_integrations:
        project = project_repository.get_project(project_integration.project_id)
        if project is None:
            logger.warning(
                "[ToastWebhook._find_toast_project_integrations_by_restaurant_guid] "
                "Project %s not found for project integration %s",
                project_integration.project_id,
                project_integration.id,
            )
            continue
        project_pairs.append((project, project_integration))

    return project_pairs


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

    # Find section boundaries using shared helper
    boundaries = _find_section_boundaries(content, start_header, end_header)
    if boundaries is None:
        # This shouldn't happen since we checked above, but handle gracefully
        return content

    section_start, section_end, full_section_end, has_end_marker = boundaries

    # Extract current section content
    section = content[section_start:section_end]
    # Pattern for exact item name matching
    # Matches: "- Item Name is OUT OF STOCK..." to end of line including newline
    # Uses \s+ to handle any whitespace between name and "is OUT OF STOCK"
    # (?:\r?\n|$) forces match to end of line and consumes newline if present
    # This prevents partial line matches that would leave dangling text
    item_pattern = rf"^- {re.escape(item_name)}\s+is OUT OF STOCK.*?(?:\r?\n|$)"

    if stock_message is not None:
        # Adding or updating item
        if re.search(item_pattern, section, re.MULTILINE):
            # Item exists, update it
            new_section = re.sub(
                item_pattern, f"{stock_message}\n", section, flags=re.MULTILINE
            )
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
        new_section = re.sub(item_pattern, "", section, flags=re.MULTILINE)

        if new_section == section:
            logger.warning(
                f"[_update_stock_section] Pattern did not match any item in section for '{item_name}' (guid: {item_guid}). "
                f"Item may have different name in database or was manually edited."
            )

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
            raw_item_name = item_data.get("name", f"Toast Item {item_guid}")
            # Normalize whitespace to prevent matching issues
            item_name = (
                " ".join(raw_item_name.split())
                if raw_item_name
                else f"Toast Item {item_guid}"
            )
            # Strip trailing punctuation (., !, ?) to handle Toast API inconsistencies
            # Toast sometimes returns "Item Name." and sometimes "Item Name"
            item_name = item_name.rstrip(".!?")
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


def _find_section_boundaries(
    content: str, start_marker: str, end_marker: str
) -> tuple[int, int, int, bool] | None:
    """
    Find the boundaries of a section marked by start and end markers.

    Handles both modern format (with end marker) and legacy format (without end marker).
    For legacy format, finds the next ### header to determine section end.

    Args:
        content: The content to search in
        start_marker: The section start marker (e.g., "### OUT-OF-STOCK ###")
        end_marker: The section end marker (e.g., "### OUT-OF-STOCK-ENDS ###")

    Returns:
        Tuple of (section_start, section_end, full_section_end, has_end_marker) where:
        - section_start: Index after the start marker (content begins here)
        - section_end: Index where section content ends (before end marker or next header)
        - full_section_end: Index after end marker (or same as section_end for legacy)
        - has_end_marker: True if end marker was found
        Returns None if start marker is not found
    """
    if start_marker not in content:
        return None

    start_idx = content.find(start_marker)
    section_start = start_idx + len(start_marker)
    end_marker_pos = content.find(end_marker, section_start)

    if end_marker_pos != -1:
        # Modern format with end marker
        section_end = end_marker_pos
        full_section_end = end_marker_pos + len(end_marker)
        has_end_marker = True
    else:
        # Legacy format without end marker: find the next header or use end of content
        next_header_match = re.search(r"^###\s+", content[section_start:], re.MULTILINE)
        if next_header_match:
            section_end = section_start + next_header_match.start()
        else:
            section_end = len(content)
        full_section_end = section_end
        has_end_marker = False

    return (section_start, section_end, full_section_end, has_end_marker)


def _extract_out_of_stock_section(content: str) -> str:
    """
    Extract the OUT-OF-STOCK section from product_info content.

    Args:
        content: The product_info content

    Returns:
        The OUT-OF-STOCK section if it exists, empty string otherwise
    """
    start_marker = "### OUT-OF-STOCK ###"
    end_marker = "### OUT-OF-STOCK-ENDS ###"

    boundaries = _find_section_boundaries(content, start_marker, end_marker)
    if boundaries is None:
        return ""

    section_start, section_end, full_section_end, has_end_marker = boundaries

    # Include the start marker and end marker (if present) in the extraction
    start_idx = content.find(start_marker)
    return content[start_idx:full_section_end]


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
            # Use populate_existing() to force SQLAlchemy to refresh the object from the database,
            # bypassing the identity map cache. This is critical when multiple concurrent webhooks
            # are updating the same project - without it, a transaction may read stale data from
            # the identity map even after acquiring the lock, causing lost updates.
            locked = (
                session.query(Project)
                .filter(Project.id == project.id)
                .populate_existing()
                .with_for_update(nowait=False)
                .one()
            )

            current_content = locked.product_info or ""

            # Update stock section based on status
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

            # Check if content changed and update database
            content_changed = new_content != current_content

            if content_changed:
                locked.product_info = new_content
                session.add(locked)
            else:
                logger.warning(
                    f"[ToastWebhook._update_stock_in_project_product_info] Content unchanged for project '{project.name}' - item '{item_name}' (guid: {item_guid}) was not found or already removed"
                )

        # Commit all changes
        session.commit()

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

    await run_in_threadpool(_process_menu_update_sync, menu_details)


def _process_menu_update_sync(menu_details: ToastWebhookMenuDetails) -> None:
    """Download, compile, and persist Toast menu assets for a menu webhook."""
    with SyncSessionLocal() as session:
        try:
            project_integrations = _find_toast_project_integrations_by_restaurant_guid(
                menu_details.restaurantGuid, session
            )

            project_integrations_to_update = [
                (project, project_integration)
                for project, project_integration in project_integrations
                if _get_auto_update_menu_on_webhook(project_integration.config)
                and _is_incoming_menu_newer(
                    _get_menu_last_updated(project_integration.config),
                    menu_details.publishedDate,
                )
            ]

            if not project_integrations_to_update:
                return

            bearer_token = get_toast_access_token_from_aws()
            raw_menu = download_menu(bearer_token, menu_details.restaurantGuid)

            for project, project_integration in project_integrations_to_update:
                selected_menus = _get_selected_menus(project_integration.config)
                make_unique_menus = (
                    selected_menus
                    if _get_make_unique(project_integration.config)
                    else None
                )
                compiled_menu = compile_toast_menu_v2(
                    raw_menu,
                    selected_menus=selected_menus,
                    make_unique_menus=make_unique_menus,
                    remove_unused_weights=True,
                )
                prompt_context = build_toast_lookup_prompt_context_markdown(
                    compiled_menu
                )
                project.product_info = prompt_context
                project_integration.config = _update_toast_menu_config(
                    project_integration.config,
                    compiled_menu,
                    menu_details.publishedDate,
                )
                session.add(project)
                session.add(project_integration)

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(
                "[ToastWebhook._process_menu_update_sync] Error processing menu update "
                "for restaurant %s: %s",
                menu_details.restaurantGuid,
                e,
            )
            raise


def _get_selected_menus(config: dict[str, Any] | None) -> list[str] | None:
    """Return configured Toast menu names to include in compiled menu assets."""
    config = config or {}
    raw_value = config.get("selected_menus")
    if raw_value is None:
        # Legacy key from the earlier selected-menu config shape.
        raw_value = config.get("menus")

    if isinstance(raw_value, str):
        raw_value = [raw_value]
    if not isinstance(raw_value, list):
        return None

    menu_names = [menu for menu in raw_value if isinstance(menu, str) and menu]
    if menu_names:
        return menu_names

    return None


def _get_make_unique(config: dict[str, Any] | None) -> bool:
    """Return whether selected Toast menus should keep duplicate items unique."""
    config = config or {}
    make_unique = config.get("make_unique")
    if isinstance(make_unique, bool):
        return make_unique
    return True


def _get_auto_update_menu_on_webhook(config: dict[str, Any] | None) -> bool:
    """Return whether Toast menu webhooks should update stored menu assets."""
    config = config or {}
    auto_update_menu_on_webhook = config.get("auto_update_menu_on_webhook")
    if isinstance(auto_update_menu_on_webhook, bool):
        return auto_update_menu_on_webhook
    return True


def _get_menu_last_updated(config: dict[str, Any] | None) -> str | None:
    """Read the last Toast menu webhook published date from integration config."""
    if not config:
        return None
    menu_last_updated = config.get("menu_last_updated")
    if not isinstance(menu_last_updated, str):
        return None
    return menu_last_updated


def _is_incoming_menu_newer(
    existing_last_updated: str | None, incoming_published_date: str
) -> bool:
    """Return whether a Toast menu webhook should replace stored menu assets."""
    if existing_last_updated is None:
        return True

    try:
        existing_dt = datetime.fromisoformat(
            existing_last_updated.replace("Z", "+00:00")
        )
        incoming_dt = datetime.fromisoformat(
            incoming_published_date.replace("Z", "+00:00")
        )
        return incoming_dt > existing_dt
    except (TypeError, ValueError):
        return existing_last_updated != incoming_published_date


def _update_toast_menu_config(
    config: dict[str, Any] | None,
    menu_data: dict[str, Any],
    menu_last_updated: str,
) -> dict[str, Any]:
    """Return updated Toast integration config with compiled menu assets."""
    updated_config = dict(config or {})
    updated_config["menu_data"] = menu_data
    updated_config["menu_last_updated"] = menu_last_updated
    return updated_config


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

    with SyncSessionLocal() as session:
        try:
            # Find the projects associated with this restaurant using ProjectIntegration table
            projects = _find_projects_by_restaurant_guid(restaurant_guid, session)

            if not projects:
                return

            # Get item name from Toast Config API
            item_name = f"Toast Item {item_guid}"  # fallback

            try:
                item_name = _get_item_name_from_toast_api(item_guid, restaurant_guid)
            except Exception as e:
                logger.warning(
                    f"[ToastWebhook._process_stock_item_status_sync] Error retrieving item name from Toast API, using fallback: {e}"
                )

            # Update the stock item status in project product_info fields
            _update_stock_in_project_product_info(
                projects, item_name, item_guid, status, session
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

            session.commit()

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

    # Format the schedule into human-readable text
    formatted_schedule = _format_ordering_schedule(
        ordering_schedule.servicePeriods,
        ordering_schedule.overrides,
    )

    # Store in database (run in threadpool to avoid blocking)
    await run_in_threadpool(
        _store_ordering_schedule_in_db,
        restaurant_guid,
        formatted_schedule,
    )


async def _process_partner_added_event(
    partner_details: ToastWebhookPartnerDetails,
) -> None:
    """
    Process partner_added event - when integration is added to a restaurant.

    Args:
        partner_details: The partner event details
    """
    restaurant_guid = partner_details.restaurantGuid
    restaurant_name = partner_details.restaurantName
    location_name = partner_details.locationName or "N/A"

    # Insert webhook data into database
    try:
        from db.session import AsyncSessionLocal
        from db.tables.onboarding_webhook_event import OnboardingWebhookEvent
        from db.tables.types import OnboardingStatus

        async with AsyncSessionLocal() as session:
            # Exclude fields we're storing explicitly to avoid duplication
            extra_data = partner_details.model_dump(
                exclude={
                    "restaurantGuid",
                    "createdByFirstName",
                    "createdByLastName",
                    "createdByEmailAddress",
                    "createdByPhoneNumber",
                    "restaurantPhoneNumber",
                }
            )

            webhook_event = OnboardingWebhookEvent(
                src="toast",
                restaurant_guid=partner_details.restaurantGuid,
                created_by_first_name=partner_details.createdByFirstName,
                created_by_last_name=partner_details.createdByLastName,
                created_by_email_address=partner_details.createdByEmailAddress,
                created_by_phone_number=partner_details.createdByPhoneNumber,
                restaurant_phone_number=partner_details.restaurantPhoneNumber,
                extra=extra_data,
                account_id=None,  # Backfilled later
                project_id=None,  # Backfilled later
                onboarding_status=OnboardingStatus.pending,
            )
            session.add(webhook_event)
            await session.commit()
    except Exception as e:
        logger.error(
            f"[ToastWebhook._process_partner_added_event] Failed to store webhook event: {e}",
            exc_info=True,
        )
        # Don't raise - webhook should still succeed

    # Send Slack notification for partner_added event
    try:
        from datetime import datetime, timezone

        from services.slack_service import (
            get_slack_channel_from_env_key,
            send_slack_message,
        )

        # Get the appropriate channel for integration events
        channel = get_slack_channel_from_env_key("TOAST_NEW_CUSTOMER_SLACK_CHANNEL")

        # Build creator info
        creator_name = "N/A"
        if partner_details.createdByFirstName or partner_details.createdByLastName:
            first = partner_details.createdByFirstName or ""
            last = partner_details.createdByLastName or ""
            creator_name = f"{first} {last}".strip()

        creator_email = partner_details.createdByEmailAddress or "N/A"
        creator_phone = partner_details.createdByPhoneNumber or "N/A"

        # Get event timestamp, fallback to current time if not available
        event_timestamp = (
            partner_details.isoCreatedDate or datetime.now(timezone.utc).isoformat()
        )

        # Build the Slack message blocks
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🍞 *Toast Integration Activated*\n{restaurant_name} has connected their Toast POS system",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"• *Restaurant:* {restaurant_name}\n"
                        f"• *Location:* {location_name}\n"
                        f"• *GUID:* {restaurant_guid}\n"
                        f"• *Timestamp:* {event_timestamp}"
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Created By:*\n"
                        f"• *Name:* {creator_name}\n"
                        f"• *Email:* {creator_email}\n"
                        f"• *Phone:* {creator_phone}"
                    ),
                },
            },
            {"type": "divider"},
        ]

        # Send the notification
        result = await send_slack_message(
            blocks=blocks,
            channel=channel,
            text_fallback=f"Toast Integration Activated for {restaurant_name}",
        )

        if result["status"] != "success":
            logger.warning(
                f"[ToastWebhook._process_partner_added_event] Failed to send Slack notification: {result.get('message')}"
            )
    except Exception as e:
        # Log error but don't fail the webhook processing
        logger.error(
            f"[ToastWebhook._process_partner_added_event] Error sending Slack notification: {e}"
        )

    # Additional business logic:
    # - Creating/updating project integrations in the database
    # - Triggering menu sync processes
    # - Setting up initial configuration


def _process_partner_removed_event(partner_details: ToastWebhookPartnerDetails) -> None:
    """
    Process partner_removed event - when integration is removed from a restaurant.

    Args:
        partner_details: The partner event details
    """
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

    # Process the event based on type
    try:
        match event_type:
            case ToastPartnerEventType.PARTNER_ADDED:
                await _process_partner_added_event(partner_details)
            case ToastPartnerEventType.PARTNER_REMOVED:
                _process_partner_removed_event(partner_details)
            case ToastPartnerEventType.PARTNER_UPDATED:
                _process_partner_updated_event(partner_details)

    except Exception as e:
        logger.error(
            f"[ToastWebhook.process_partner_event] Error processing partner event {event_type}: {e}"
        )
        raise
