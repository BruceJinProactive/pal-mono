from datetime import date, time
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from db.repositories.catering_request_repository import CateringRequestRepository
from db.session import SyncSessionLocal
from db.tables.catering_requests import FulfillmentType
from services.catering_service import create_catering_request, send_sms_notification
from utils.log import logger

CALLER_CONFIRMATION_MESSAGE = (
    "Thanks for reaching out. Your catering request has been recorded and sent to the store. "
    "Someone will get back to you soon."
)


class CateringTool(Toolkit):
    def __init__(self, tool_metadata: ToolMetadata):
        super().__init__(name="catering_tool")
        self.tool_metadata = tool_metadata

        # Register tools
        self.register(self.create_catering_request)

    @tool
    def create_catering_request(
        self,
        event_date: str,  # YYYY-MM-DD format
        contact_name: str,
        contact_phone_number: str,
        party_size: int,
        event_time: Optional[str] = None,  # HH:MM format
        event_address: Optional[str] = None,
        event_detail: Optional[str] = None,
        event_fulfillment: Optional[str] = None,  # "DELIVERY" or "PICKUP"
    ) -> str:
        """
        Create a new catering request for an event. Store all order and event details in `event_detail`,
        including menu items, quantities, customizations, dietary notes, special requests, and any relevant context

        **WHEN TO USE THIS TOOL:**
        - When a customer wants to place a catering request for an event
        - When all required information (event_date, contact_name, contact_phone_number, party_size) has been collected

        **REQUIRED INFORMATION:**
        - event_date: Date of the event (YYYY-MM-DD format, e.g., "2024-12-25")
        - contact_name: Name of the contact person
        - contact_phone_number: Phone number of the contact person
        - party_size: Number of people expected at the event

        **OPTIONAL INFORMATION:**
        - event_time: Time of the event (HH:MM format, e.g., "14:30")
        - event_address: Address where the event will take place
        - event_detail: Additional details about the event; **include all customer order details here**
        - event_fulfillment: How the catering will be fulfilled ("DELIVERY" or "PICKUP")

        Returns:
            str: Success message with catering request details, or error message
        """
        try:
            # Get project_id from tool metadata
            project_id = self.tool_metadata.project_id
            if not project_id:
                return "Error: No project_id available in tool metadata."

            # Validate required fields
            if (
                not event_date
                or not contact_name
                or not contact_phone_number
                or party_size is None
            ):
                return "Error: event_date, contact_name, contact_phone_number, and party_size are required fields."

            # Parse and validate event_date
            try:
                parsed_event_date = date.fromisoformat(event_date)
            except ValueError:
                return f"Error: Invalid event_date format: {event_date}. Use YYYY-MM-DD format"

            # Parse and validate event_time if provided
            parsed_event_time = None
            if event_time:
                try:
                    parsed_event_time = time.fromisoformat(event_time)
                except ValueError:
                    return f"Error: Invalid event_time format: {event_time}. Use HH:MM format"

            # Parse and validate event_fulfillment if provided
            parsed_event_fulfillment = None
            if event_fulfillment:
                if event_fulfillment.upper() in ["DELIVERY", "PICKUP"]:
                    parsed_event_fulfillment = FulfillmentType(
                        event_fulfillment.upper()
                    )
                else:
                    return f"Error: Invalid event_fulfillment: {event_fulfillment}. Must be 'DELIVERY' or 'PICKUP'"

            raw_session_id = getattr(self.tool_metadata, "session_id", None)
            idempotency_key = str(raw_session_id) if raw_session_id else None
            request_already_exists = False

            # Pre-check for idempotent replay to avoid sending duplicate caller SMS.
            if idempotency_key:
                with SyncSessionLocal() as precheck_session:
                    existing_request = CateringRequestRepository(
                        precheck_session
                    ).get_catering_request_by_idempotency_key(idempotency_key)
                    request_already_exists = existing_request is not None

            catering_request = create_catering_request(
                project_id=project_id,
                event_date=parsed_event_date,
                contact_name=contact_name,
                contact_phone_number=contact_phone_number,
                event_time=parsed_event_time,
                event_address=event_address,
                event_detail=event_detail,
                event_fulfillment=parsed_event_fulfillment,
                party_size=party_size,
                idempotency_key=idempotency_key,
            )

            caller_phone = (
                self.tool_metadata.customer_phone or contact_phone_number or None
            )
            if request_already_exists:
                logger.debug(
                    "[CateringTool.create_catering_request] "
                    "Idempotent replay detected; skipping duplicate caller confirmation SMS.",
                    extra={
                        "project_id": str(project_id),
                        "request_id": str(catering_request.id),
                        "idempotency_key": idempotency_key,
                    },
                )
            elif caller_phone:
                sms_sent = send_sms_notification(
                    caller_phone,
                    CALLER_CONFIRMATION_MESSAGE,
                )
                if not sms_sent:
                    logger.warning(
                        "[CateringTool.create_catering_request] "
                        "Created request but failed to send caller confirmation SMS.",
                        extra={
                            "project_id": str(project_id),
                            "request_id": str(catering_request.id),
                        },
                    )
            else:
                logger.warning(
                    "[CateringTool.create_catering_request] "
                    "Created request but caller phone is unavailable; skipping confirmation SMS.",
                    extra={
                        "project_id": str(project_id),
                        "request_id": str(catering_request.id),
                    },
                )

            return f"✅ Catering request created successfully! Request ID: {catering_request.id}"

        except Exception as e:
            logger.error(f"[CateringTool.create_catering_request] Error: {e}")
            return f"Failed to create catering request: {str(e)}"
