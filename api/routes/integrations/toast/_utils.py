import os
import re

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores.types import (
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from db.repositories.agent_repository import AgentRepository
from db.session import SyncSessionLocal
from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider
from services.admin_service._utils import _get_agent_knowledge_settings
from services.auth_types import UserContext, UserRole
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


def _get_project_pinecone_settings(
    project: Project, session: Session
) -> tuple[str | None, str | None]:
    """
    Get Pinecone index name and namespace from project's agent configuration.

    Args:
        project: The project object
        session: Database session

    Returns:
        Tuple of (index_name, namespace) or (None, None) if not found
    """
    try:
        if not project.agent_id:
            logger.warning(
                f"[ToastWebhook._get_project_pinecone_settings] No agent_id found in project: {project.id}"
            )
            return None, None

        # Get the agent
        agent_repo = AgentRepository(session, auto_commit=False)
        agent = agent_repo.get_agent(project.agent_id)

        if not agent:
            logger.warning(
                f"[ToastWebhook._get_project_pinecone_settings] No agent found for agent_id: {project.agent_id}"
            )
            return None, None

        # Create a mock UserContext for the admin service function
        mock_context = UserContext(
            username="toast-webhook-system",
            email="noreply@toast-webhook",
            groups=[],
            display_name="Toast Webhook System",
            account_names=[agent.account.name],
            role=UserRole.Admin,
        )

        index_name, namespace = _get_agent_knowledge_settings(
            session=session,
            context=mock_context,
            target=agent,
            auto_create=False,  # Don't auto-create in webhook context
        )

        logger.debug(
            f"[ToastWebhook._get_project_pinecone_settings] Project {project.name} Pinecone settings - Index: {index_name}, Namespace: {namespace}"
        )
        return index_name, namespace

    except Exception as e:
        logger.error(
            f"[ToastWebhook._get_project_pinecone_settings] Error getting Pinecone settings for project {project.id}: {e}"
        )
        return None, None


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
    item_pattern = (
        rf"- {re.escape(item_name)} \(ID: {re.escape(item_guid)}\).*?(\r?\n|$)"
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


def _get_item_name_from_pinecone(
    item_guid: str, index_name: str, namespace: str
) -> str:
    """
    Retrieve item name from Pinecone knowledge base using itemGuid.

    Args:
        item_guid: Toast item GUID
        index_name: Pinecone index name
        namespace: Pinecone namespace

    Returns:
        Item name from file_name metadata or fallback name
    """
    try:
        # Initialize Pinecone and vector store
        pc = Pinecone(os.getenv("PINECONE_API_KEY"))
        pinecone_index = pc.Index(index_name)
        vector_store = PineconeVectorStore(
            pinecone_index=pinecone_index, namespace=namespace
        )

        cohere_key = os.getenv("COHERE_API_KEY")
        if not cohere_key:
            logger.warning(
                "[ToastWebhook._get_item_name_from_pinecone] COHERE_API_KEY is missing; falling back to Unknown Item."
            )
            return f"Unknown Item ({item_guid})"

        embed_model = CohereEmbedding(
            api_key=cohere_key,
            model_name="embed-english-v3.0",
        )

        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=embed_model,
        )

        # Create retriever with metadata filter for itemGuid
        retriever = index.as_retriever(
            similarity_top_k=1,
            filters=MetadataFilters(
                filters=[
                    MetadataFilter(
                        key="itemGuid", value=item_guid, operator=FilterOperator.EQ
                    )
                ]
            ),
        )

        # Query for the item
        nodes = retriever.retrieve("menu item")
        if not nodes:
            logger.warning(
                f"[ToastWebhook._get_item_name_from_pinecone] No menu item found for itemGuid: {item_guid}"
            )
            return f"Unknown Item ({item_guid})"

        # Extract item name from metadata
        item_name = nodes[0].metadata.get("file_name", f"Item ({item_guid})")
        logger.debug(
            f"[ToastWebhook._get_item_name_from_pinecone] Found item name from Pinecone: {item_name} for itemGuid: {item_guid}"
        )
        return item_name

    except Exception as e:
        logger.warning(
            f"[ToastWebhook._get_item_name_from_pinecone] Could not retrieve item from Pinecone vector store: {e}"
        )
        return f"Unknown Item ({item_guid})"


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
                stock_message = f"- {item_name} (ID: {item_guid}) is OUT OF STOCK. You MUST NOT accept orders for this item under any circumstances."
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
    This function contains all the blocking DB and Pinecone operations.
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
                logger.error(
                    f"[ToastWebhook._process_stock_item_status_sync] Could not find any projects for restaurant_guid: {restaurant_guid}"
                )
                return

            # Get item name from Pinecone knowledge base using the first project's settings
            item_name = f"Toast Item {item_guid}"  # fallback

            try:
                # Use the first project to get Pinecone settings
                # (all projects for same restaurant should have same knowledge base)
                first_project = projects[0]
                index_name, namespace = _get_project_pinecone_settings(
                    first_project, session
                )

                if index_name and namespace:
                    item_name = _get_item_name_from_pinecone(
                        item_guid, index_name, namespace
                    )
                else:
                    logger.warning(
                        f"[ToastWebhook._process_stock_item_status_sync] Could not get Pinecone settings for project {first_project.name}, using fallback item name"
                    )

            except Exception as e:
                logger.warning(
                    f"[ToastWebhook._process_stock_item_status_sync] Error retrieving item name from Pinecone, using fallback: {e}"
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
    scheduled_order_max_days = ordering_schedule.scheduledOrderMaxDays
    last_order_configuration = ordering_schedule.lastOrderConfiguration

    logger.debug(
        f"[ToastWebhook.update_ordering_schedule] Restaurant {restaurant_guid} updated ordering schedule to {ordering_schedule}. "
        f"Scheduled order max days: {scheduled_order_max_days}. "
        f"Last order configuration: {last_order_configuration}."
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
