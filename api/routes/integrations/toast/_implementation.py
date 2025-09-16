import json

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from db.tables import Integration, IntegrationProvider, Project, ProjectIntegration
from services.knowledge_service import (
    delete_knowledge_file_by_metadata,
    query_vector_database,
    upload_knowledge_file,
)
from tools.toast_tool._apis import connect_toast_order_hub
from tools.toast_tool._utils import get_toast_access_token_from_aws
from tools.utils.ordering.classes import HttpMethod
from utils.log import logger

from ._utils import (
    process_partner_event,
    update_menu_content,
    update_ordering_schedule,
    update_stock_item_status,
)
from .schema import ToastWebhookRequest, ToastWebhookResponse


def _are_dining_options_same(
    api_response_raw: str, kb_dining_options_text: str
) -> bool:
    """
    Compare dining options raw response from Toast API with those stored in KB.

    Args:
        api_response_raw: Raw string response from Toast API
        kb_dining_options_text: String containing raw dining options from KB

    Returns:
        bool: True if dining options are same, False if they are different
    """
    try:
        # Direct string comparison since both should be the same raw format
        return api_response_raw.strip() == kb_dining_options_text.strip()

    except Exception as e:
        logger.error(
            f"[ToastAPIIntegration._are_dining_options_same] Error comparing dining options: {e}"
        )
        # On error, assume they are different
        return False


async def api_toast_webhook(request: Request) -> JSONResponse:
    """
    Process incoming webhook requests from Toast.
    Authentication and validation are handled by AWS API Gateway.

    Args:
        request: The FastAPI request object

    Returns:
        JSONResponse: The response to send back to Toast

    Raises:
        HTTPException: If there's an error processing the request
    """
    # Extract body from request
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid JSON in request body: {str(e)}"},
        )

    # Validate request body against schema
    try:
        webhook_request = ToastWebhookRequest(**body)

        # Handle webhook events
        match webhook_request.eventCategory:
            case "menus":
                await update_menu_content(webhook_request)
            case "stock":
                await update_stock_item_status(webhook_request)
            case "ordering_schedule":
                await update_ordering_schedule(webhook_request)
            case "partner":
                await process_partner_event(webhook_request)
            case _:
                logger.warning(
                    f"[ToastWebhook.api_toast_webhook] Received unknown Toast webhook event category: {webhook_request.eventCategory}"
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=ToastWebhookResponse().model_dump(exclude_none=True),
                )
    except ValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Invalid request body: {str(e)}"},
        )

    # Log the incoming request for debugging
    logger.debug(
        "[ToastWebhook.api_toast_webhook] Toast webhook request received",
        extra={
            "timestamp": webhook_request.timestamp,
            "event_category": webhook_request.eventCategory,
            "event_type": webhook_request.eventType,
            "guid": webhook_request.guid,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ToastWebhookResponse().model_dump(exclude_none=True),
    )


def _fetch_dining_options(integration: Integration) -> str | None:
    """Fetch dining options from Toast API for given integration."""
    if not integration.business_id:
        logger.warning(
            "[ToastAPIIntegration._fetch_dining_options] Integration has no business ID, skipping"
        )
        return None

    try:
        bearer_token = get_toast_access_token_from_aws(store_id=integration.business_id)
        response = connect_toast_order_hub(
            http_method=HttpMethod.GET,
            bearer_token=bearer_token,
            api_function="/config/v2/diningOptions",
            store_id=integration.business_id,
            query_params=None,
            payload=None,
        )

        if response.status != 200:
            raise Exception(f"Toast API returned status {response.status}")

        return response.decoded_body

    except Exception as e:
        logger.error(
            "[ToastAPIIntegration._fetch_dining_options] Failed to fetch dining options for store %s: %s",
            integration.business_id,
            e.__class__.__name__,
            exc_info=True,
        )
        return None


def _upload_dining_options_to_kb(
    index_name: str, namespace: str, dining_options_raw: str
):
    """Upload dining options to knowledge base."""
    upload_knowledge_file(
        index_name=index_name,
        namespace=namespace,
        file_name="dining_options.txt",
        content=dining_options_raw.encode("utf-8"),
        metadata={"isDiningOptions": True},
    )


def _refresh_dining_options_in_kb(
    index_name: str, namespace: str, dining_options_raw: str
):
    """Delete existing dining options and upload new ones."""
    delete_knowledge_file_by_metadata(
        index_name=index_name,
        namespace=namespace,
        metadata={"isDiningOptions": {"$eq": True}},
    )
    _upload_dining_options_to_kb(index_name, namespace, dining_options_raw)


def _update_project_dining_options(
    project: Project, integration: Integration, dining_options_raw: str
):
    """Update dining options in project's knowledge base if needed."""
    raw_config = project.raw_config
    project_tools = raw_config.get("tools", {}).get("identifiers", [])

    for project_tool in project_tools:
        if project_tool.get("tool_name") != "toast_tool":
            continue

        namespace = project_tool.get("namespace")
        index_name = project_tool.get("index_name")

        if not (namespace and index_name):
            continue

        # Query KB for existing dining options
        result = query_vector_database(
            index_name=index_name,
            namespace=namespace,
            query="dining options",
            top_k=3,
        )

        if not result:
            logger.warning(
                "[ToastAPIIntegration._update_project_dining_options] No KB result; refreshing from API for store %s",
                integration.business_id,
            )
            _upload_dining_options_to_kb(index_name, namespace, dining_options_raw)
            return

        # Look for existing dining options
        for match in result:
            match_metadata = match.get("metadata", {})
            if not match_metadata.get("isDiningOptions", False):
                continue

            logger.debug(
                "[ToastAPIIntegration._update_project_dining_options] Dining options found in KB for store %s with metadata %s",
                integration.business_id,
                match_metadata,
            )

            kb_dining_options = match_metadata.get("text")
            if not kb_dining_options:
                logger.warning(
                    "[ToastAPIIntegration._update_project_dining_options] KB match missing text; re-uploading for store %s",
                    integration.business_id,
                )
                _refresh_dining_options_in_kb(index_name, namespace, dining_options_raw)
                return

            # Compare and update if different
            if not _are_dining_options_same(dining_options_raw, kb_dining_options):
                logger.debug(
                    "[ToastAPIIntegration._update_project_dining_options] Updating dining options for store %s",
                    integration.business_id,
                )
                _refresh_dining_options_in_kb(index_name, namespace, dining_options_raw)
            else:
                logger.debug(
                    "[ToastAPIIntegration._update_project_dining_options] Dining options match for store %s",
                    integration.business_id,
                )
            return

        # No dining options found, create new ones
        logger.debug(
            "[ToastAPIIntegration._update_project_dining_options] No dining options found; creating for store %s",
            integration.business_id,
        )
        _refresh_dining_options_in_kb(index_name, namespace, dining_options_raw)


def check_and_refresh_dining_options(session):
    """Check and refresh dining options for all Toast integrations."""
    integrations = (
        session.query(Integration)
        .filter(Integration.provider == IntegrationProvider.toast)
        .all()
    )

    for integration in integrations:
        dining_options_raw = _fetch_dining_options(integration)
        if not dining_options_raw:
            continue

        projects = (
            session.query(Project)
            .join(ProjectIntegration)
            .filter(ProjectIntegration.integration_id == integration.id)
            .all()
        )

        for project in projects:
            _update_project_dining_options(project, integration, dining_options_raw)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Dining options successfully checked"},
    )
