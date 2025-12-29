import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from vapi import AsyncVapi

import db
from api.schemas.chat.message import (
    AuthorType,
    Extras,
    Message,
    Metadata,
    TextObject,
    Type,
)
from db.repositories.conversation_repository import ConversationUpdate
from db.tables.types import Channel
from services import (
    message_service,
    project_service,
    subscription_service,
    user_service,
)
from services.message_service._utils import transform_vapi_conversation_data
from services.subscription_service import _stripe_product
from services.subscription_service.stripe_usage_billing import send_meter_event
from utils.dd import dd_histogram_duration
from utils.log import logger


def _get_squad_model(squad_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Get the squad model from the squad data.
    """
    # Get language assistant model name from the second member of squad_data.
    # The first member is the triage assistant, and all subsequent members function as language assistants.
    members = squad_data.get("members", [])
    if len(members) < 2:
        logger.error("Squad has fewer than two members; cannot extract language model")
        return None

    if not isinstance(members[1], dict):
        logger.error("Squad member at index 1 is not a dict; cannot extract model")
        return None

    language_assistant = members[1].get("assistant")
    if not isinstance(language_assistant, dict):
        logger.error("Squad member assistant is not a dict; cannot extract model")
        return None

    model_block = language_assistant.get("model")

    return model_block


def _get_vapi_client() -> AsyncVapi:
    """
    Get the VAPI client.
    """
    vapi_token = os.environ.get("VAPI_API_KEY")
    if not vapi_token:
        raise ValueError("VAPI_API_KEY environment variable is required")

    return AsyncVapi(token=vapi_token)


def _format_assistant_name(base_name: str, suffix: str, max_length: int = 40) -> str:
    """
    Format an assistant name by truncating the base name if necessary to fit within max_length.

    This helper ensures that assistant/squad names with suffixes don't exceed VAPI's
    character limits during self-onboarding.

    Args:
        base_name: The base name to be formatted
        suffix: The suffix to append (e.g., " (English)", " (Language Triage)")
        max_length: Maximum total length allowed (default: 40)

    Returns:
        str: Formatted name with suffix, truncated if necessary

    Example:
        >>> _format_assistant_name("Very Long Restaurant Name", " (English)", 40)
        "Very Long Restaurant Name (English)"
        >>> _format_assistant_name("Very Long Restaurant Name Here", " (Spanish)", 40)
        "Very Long Restaurant N (Spanish)"
    """
    max_base_len = max_length - len(suffix)
    truncated_base = (
        base_name[:max_base_len] if len(base_name) > max_base_len else base_name
    )
    return f"{truncated_base}{suffix}"


def _get_webhook_config() -> tuple[str, str, list[str]]:
    """
    Resolve webhook configuration from environment variables.

    Returns:
        tuple[str, str, list[str]]: (webhook_url, bearer_token, allowed_business_numbers)
    """
    # Resolve from environment variables. If missing, disable.
    webhook_url = os.getenv("SALES_AGENT_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("SALES_AGENT_WEBHOOK_URL not set; hangup webhook disabled")

    bearer_token = os.getenv("SALES_AGENT_WEBHOOK_BEARER_TOKEN", "")
    if not bearer_token:
        logger.warning(
            "SALES_AGENT_WEBHOOK_BEARER_TOKEN not set; hangup webhook disabled"
        )

    # Allow a single number only
    single = os.getenv("SALES_AGENT_WEBHOOK_BUSINESS_NUMBER", "")
    if not single:
        logger.debug("SALES_AGENT_WEBHOOK_BUSINESS_NUMBER not configured")
    allowed_numbers: list[str] = []
    if single.strip():
        allowed_numbers = [single.strip()]
    # If none provided, keep allowlist empty (webhook will be disabled by caller condition)

    return webhook_url, bearer_token, allowed_numbers


def _is_allowed_business_number(phone_number: str, allowed_numbers: list[str]) -> bool:
    # Compare normalized E.164 strings (assume inputs are already E.164)
    return phone_number in set(allowed_numbers)


async def _post_hangup_webhook(payload: dict) -> bool:
    webhook_url, bearer_token, _ = _get_webhook_config()
    if not webhook_url or not bearer_token:
        logger.warning(
            "Webhook URL or token missing; skipping hangup webhook",
            extra={"call_id": payload.get("call_id")},
        )
        return False
    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or not parsed.netloc:
        logger.warning(
            "Invalid webhook URL; must be HTTPS with host",
            extra={"call_id": payload.get("call_id")},
        )
        return False

    # Basic SSRF hardening: block local/privately scoped addresses
    host = parsed.hostname or ""
    try:
        from ipaddress import ip_address

        ip = ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            logger.warning(
                "Invalid webhook URL; local/private address not allowed",
                extra={"call_id": payload.get("call_id")},
            )
            return False
    except ValueError:
        # Not an IP literal; block common local hostnames
        if host in {"localhost"} or host.endswith(".local"):
            logger.warning(
                "Invalid webhook URL; localhost/.local not allowed",
                extra={"call_id": payload.get("call_id")},
            )
            return False

    headers = {
        "X-Event-Type": "call.hangup",
        "X-Event-Version": "1",
        "X-Request-Id": str(payload.get("call_id", "")),
        "X-Idempotency-Key": str(payload.get("call_id", "")),
        "User-Agent": "pal-mono/vapi-hangup-webhook",
        "Authorization": f"Bearer {bearer_token}",
    }

    timeout = httpx.Timeout(10.0, connect=5.0)
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout, http2=True) as client:
                resp = await client.post(webhook_url, json=payload, headers=headers)
            if 200 <= resp.status_code < 300:
                return True
            retriable = resp.status_code == 429 or resp.status_code >= 500
            logger.warning(
                f"Webhook post non-2xx: status={resp.status_code}",
                extra={"call_id": payload.get("call_id")},
            )
            if retriable and attempt < 2:
                await _async_sleep(0.5 * (attempt + 1))
                continue
            return False
        except Exception as e:
            if attempt < 2:
                await _async_sleep(0.5 * (attempt + 1))
                continue
            logger.error(
                f"Failed to post webhook: {e}",
                extra={"call_id": payload.get("call_id")},
            )
            return False

    # Safety fallback to ensure all code paths return a boolean
    return False


async def _async_sleep(seconds: float) -> None:
    # Local wrapper to avoid importing asyncio at module import time
    import asyncio

    await asyncio.sleep(seconds)


async def _send_hangup_webhook_background(
    payload: dict, business_last4: str, caller_last4: str
) -> None:
    """
    Fire-and-forget sender for the hangup webhook with masked logging.
    """
    try:
        ok = await _post_hangup_webhook(payload)
        if ok:
            logger.info(
                "Hangup webhook sent",
                extra={
                    "call_id": payload.get("call_id"),
                    "business_last4": business_last4,
                    "caller_last4": caller_last4,
                },
            )
        else:
            logger.error(
                "Hangup webhook failed",
                extra={
                    "call_id": payload.get("call_id"),
                    "business_last4": business_last4,
                    "caller_last4": caller_last4,
                },
            )
    except Exception as e:
        logger.error(
            f"Hangup webhook error: {e}",
            extra={
                "call_id": payload.get("call_id"),
                "business_last4": business_last4,
                "caller_last4": caller_last4,
            },
        )


def send_dd_latency(
    log_message: str, call_id: str, customer_number: str, phone_number: str
) -> None:
    """
    Extract latency metrics from VAPI log message and send to DataDog.

    Args:
        log_message: Log message containing latency data
        call_id: Call ID for tagging
        customer_number: Customer phone number for tagging
        phone_number: Business phone number for tagging
    """
    # Extract turn latency
    turn_latency_match = re.search(r"Turn latency: (\d+)ms", log_message)
    turn_latency = int(turn_latency_match.group(1)) if turn_latency_match else None

    # Extract transcriber latency
    transcriber_match = re.search(r"transcriber: (\d+)ms", log_message)
    transcriber_latency = int(transcriber_match.group(1)) if transcriber_match else None

    # Extract model latency
    model_match = re.search(r"model: (\d+)ms", log_message)
    model_latency = int(model_match.group(1)) if model_match else None

    # Extract voice latency
    voice_match = re.search(r"voice: (\d+)ms", log_message)
    voice_latency = int(voice_match.group(1)) if voice_match else None

    logger.debug(
        f"Extracted latencies for call {call_id} (from {customer_number} to {phone_number}): turn={turn_latency}ms, transcriber={transcriber_latency}ms, model={model_latency}ms, voice={voice_latency}ms"
    )

    # Send individual metrics to DataDog
    base_tags = [
        f"call_id:{call_id}",
        f"customer_number:{customer_number}",
        f"phone_number:{phone_number}",
    ]

    if turn_latency is not None:
        dd_histogram_duration(
            name="vapi.turn_latency",
            duration_ms=turn_latency,
            tags=base_tags + ["component:total"],
        )
    else:
        logger.debug(f"Turn latency not found in log message for call {call_id}")

    if transcriber_latency is not None:
        dd_histogram_duration(
            name="vapi.transcriber_latency",
            duration_ms=transcriber_latency,
            tags=base_tags + ["component:transcriber"],
        )
    else:
        logger.debug(f"Transcriber latency not found in log message for call {call_id}")

    if model_latency is not None:
        dd_histogram_duration(
            name="vapi.model_latency",
            duration_ms=model_latency,
            tags=base_tags + ["component:model"],
        )
    else:
        logger.debug(f"Model latency not found in log message for call {call_id}")

    if voice_latency is not None:
        dd_histogram_duration(
            name="vapi.voice_latency",
            duration_ms=voice_latency,
            tags=base_tags + ["component:voice"],
        )
    else:
        logger.debug(f"Voice latency not found in log message for call {call_id}")


async def _measure_voice_to_voice_latency(message_data: dict) -> None:
    """
    Measure conversation turn-taking latency for a completed call and send metrics to DataDog.
    Distinguishes between user-to-agent and agent-to-user response latencies.

    Args:
        message_data: Message data sent from VAPI webhook
    """
    call_data = message_data.get("call", {})
    call_id = call_data.get("id")

    # Extract caller information
    customer_data = message_data.get("customer", {})
    customer_number = customer_data.get("number", "")

    # Extract business information
    phone_number_data = message_data.get("phoneNumber", {})
    phone_number = phone_number_data.get("number", "")

    # Initialize VAPI client
    vapi_token = os.environ.get("VAPI_API_KEY")
    if not vapi_token:
        logger.error("VAPI_API_KEY environment variable not set")
        return

    vapi_client = AsyncVapi(token=vapi_token)

    # Get logs for this call
    try:
        logs_pager = await vapi_client.logs.get(call_id=call_id, type="Call")

        # Collect and filter logs from the pager
        async for log in logs_pager:
            # Filter for turn latency logs
            log_level = getattr(log, "level", None)
            log_message = getattr(log, "log", None)
            if log_level == "INFO" and log_message and "Turn latency:" in log_message:
                send_dd_latency(log_message, call_id, customer_number, phone_number)

    except Exception as e:
        logger.error(f"Failed to retrieve logs for call {call_id}: {str(e)}")
        return


async def api_vapi_server(request: Request, session: AsyncSession) -> JSONResponse:
    """
    Process incoming requests from VAPI service.

    Args:
        request: The FastAPI request object
        session: The database session

    Returns:
        JSONResponse: The response to send back to VAPI

    Raises:
        HTTPException: If there's an error processing the request
    """
    try:
        # Extract body from request
        body = await request.json()

        # Validate request format
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Invalid request format"},
            )

        # Log the incoming request for debugging
        logger.debug(
            "VAPI request received",
            extra={
                "message_type": body.get("message", {}).get("type"),
                # drop / hash phone numbers & transcripts
            },
        )

        # Extract information from VAPI request structure
        message_data = body.get("message", {})
        message_type = message_data.get("type")

        # Handle different message types from VAPI
        match message_type:
            case "assistant-request":
                response_data = await handle_assistant_request(message_data, session)
            case "status-update":
                response_data = await handle_status_update(message_data, session)
            case "function-call":
                response_data = handle_function_call(message_data)
            case "transcript-update":
                response_data = handle_transcript_update(message_data)
            case "end-of-call-report":
                response_data = await handle_session_closure(message_data, session)
            case "tool-calls":
                response_data = handle_tool_calls(message_data)
            case _:
                logger.warning(f"Received unknown VAPI message type: {message_type}")
                response_data = {"status": "acknowledged"}
        return JSONResponse(content=response_data)

    except json.JSONDecodeError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid JSON in request body"},
        )
    except Exception as e:
        logger.error(f"Error processing VAPI request: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Error processing request: {str(e)}"},
        )


async def handle_assistant_request(message_data, session: AsyncSession):
    """
    Handle assistant-request message type.
    This is sent when a call starts and is waiting for initial instructions.

    Args:
        message_data: The message data from the request
        session: The database session

    Returns:
        dict: Response for VAPI with either an assistantId, a transient assistant configuration, or a workflow configuration
    """
    try:
        # Extract call information
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        # Validate call_id is present and non-empty
        if not call_id or not isinstance(call_id, str) or not call_id.strip():
            logger.error(
                "[handle_assistant_request] Invalid or missing call_id",
                extra={"call_data": call_data},
            )
            return {"error": "Invalid or missing call_id"}

        # Use `or {}` because .get() returns None if key exists with None value
        monitor_data = call_data.get("monitor") or {}

        logger.debug(
            f"[vapi._implementation.handle_assistant_request] Processing assistant request. Monitor Data: {monitor_data}"
        )

        # Extract phone number information
        phone_number_data = message_data.get("phoneNumber", {})
        phone_number = phone_number_data.get("number", "")

        # Extract customer information
        customer_data = message_data.get("customer", {})
        customer_number = customer_data.get("number", "")

        logger.debug(
            f"[vapi._implementation.handle_assistant_request] Handling assistant request for call {call_id} from {customer_number} to {phone_number}",
            extra={
                "call_id": call_id,
                "customer_number": customer_number,
                "phone_number": phone_number,
                "phone_number_data": phone_number_data,
                "customer_data": customer_data,
                "call_data": call_data,
            },
        )

        # Create a Message object for this call request
        message = Message(
            id=str(uuid.uuid4()),
            author_type=AuthorType.SYSTEM,
            # Channel information
            sender_identifier=customer_number,
            recipient_identifier=phone_number,
            channel=Channel.VOICE,
            broker=None,  # Could be set if known
            # Content
            type=Type.TEXT,
            text=TextObject(body="[Call initiated]"),
            context="",
            # Extras
            extras=Extras(),
            # Metadata
            metadata=Metadata(),
            timestamp=datetime.now(timezone.utc),
        )

        # Log the created message
        logger.debug(
            f"[vapi._implementation.handle_assistant_request] Created message: {message.id} for call {call_id}",
            extra={
                "message_id": message.id,
                "call_id": call_id,
                "customer_number": customer_number,
                "phone_number": phone_number,
            },
        )

        # ==== Step 1: Get project, user, and save request message ====
        project = await project_service.get_project_async(session, message)
        if not project:
            raise ValueError("Project not found for this message")

        # Get user_id by sender channel/number with user_service
        user, _ = await user_service.get_user_async(session, project, message)
        if not user:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)
            # Refresh to avoid MissingGreenlet error when accessing attributes after commit
            await session.refresh(user, attribute_names=["id"])
            await session.refresh(project, attribute_names=["id"])
            logger.debug(
                "[handle_assistant_request] Created new user for voice call",
                extra={
                    "call_id": call_id,
                    "user_id": str(user.id),
                    "project_id": str(project.id),
                    "customer_number": customer_number,
                },
            )

        # Refresh project after user operations (which may commit and expire objects)
        # to avoid MissingGreenlet error when accessing project.id
        await session.refresh(project, attribute_names=["id"])

        # Save request message to database
        message_repo = db.MessageRepositoryAsync(session)

        logger.debug(
            f"[vapi._implementation.handle_assistant_request] Saving request message {message.id} for user {user.id} and call {call_id} in project {project.id}",
            extra={
                "message_id": message.id,
                "user_id": str(user.id),
                "call_id": call_id,
                "project_id": str(project.id),
            },
        )
        request_message = await message_repo.create_voice_message(
            user_id=user.id,
            project_id=project.id,
            message_body=message.to_dict(),
            call_id=call_id,
        )
        await session.refresh(user, attribute_names=["id"])
        await session.refresh(project, attribute_names=["id"])

        logger.debug(
            f"[handle_assistant_request] Voice message created for call {call_id}",
            extra={
                "call_id": call_id,
                "conversation_id": str(request_message.conversation_id),
                "message_id": str(request_message.id),
                "project_id": str(project.id),
                "user_id": str(user.id),
                "customer_number": customer_number,
                "phone_number": phone_number,
            },
        )

        if not request_message:
            logger.error(
                f"[vapi._implementation.handle_assistant_request] Failed to create request message for user {user.id} and call {call_id} in project {project.id}",
            )
            raise ValueError("Failed to create request message")

        await session.refresh(project, attribute_names=["id", "account"])

        account_display_name = project.account.display_name
        # Fallback to account name if display name is not set
        if not account_display_name:
            account_display_name = project.account.name

        # ================= Step 1.5: Check subscription enforcement =================
        # Check if calls should be allowed based on subscription status
        if await subscription_service.should_block_calls_async(
            session,
            project.account,
        ):
            logger.info(
                "VAPI call blocked due to subscription enforcement for self-onboarded account",
                extra={
                    "account_id": str(project.account.id),
                    "account_name": project.account.name,
                    "account_status": project.account.status.value,
                    "onboarding_method": project.account.onboarding_method.value,
                    "has_current_subscription": project.account.current_subscription_id
                    is not None,
                    "has_stripe_customer": project.account.stripe_customer_id
                    is not None,
                    "call_id": call_id,
                    "customer_number": customer_number,
                },
            )

            return {
                "assistant": {
                    "firstMessage": "I'm sorry, but voice calls are only available for subscribed users with a valid payment method. Please visit our admin console to subscribe and add a credit card to use this feature. Thank you for your understanding.",
                    "model": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                    },
                    "voice": {"provider": "11labs", "voiceId": "sarah"},
                    "endCallMessage": "Goodbye!",
                    "endCallPhrases": [
                        "subscription required",
                        "goodbye",
                        "thank you",
                    ],
                }
            }

        # ================= Step 2: Construct agent and generate output =================
        agent_id = project.agent_id
        if not agent_id:
            raise ValueError("Agent ID not found")

        # Create caller_info with required fields for message routing
        caller_info = {
            "sender_identifier": customer_number,
            "recipient_identifier": phone_number,
            "call_id": call_id,  # Adding call_id for future reference
            "timezone": project.timezone,
        }

        # ================= Step 3: Construct assistant(s) =================

        #########################################################
        # Try to use new voice_configs table first, fallback to existing logic
        #########################################################

        try:
            # Try using the new voice configuration system
            from services import (
                voice_service,  # Lazy import to avoid circular dependency
            )

            voice_response = (
                await voice_service.VoiceService().create_vapi_assistant_response(
                    caller_info=caller_info,
                    project_id=project.id,
                    session=session,
                )
            )
            logger.debug(f"Using new voice_configs system for call {call_id}")
            return voice_response
        except Exception as e:
            logger.warning(
                f"Failed to use voice_configs system for call {call_id}, falling back to original logic: {str(e)}"
            )

    except Exception as e:
        logger.error(f"Error in handle_assistant_request: {str(e)}", exc_info=True)
        return {"error": str(e)}


async def handle_status_update(message_data, session: AsyncSession):
    """
    Handle status-update message type.
    This is sent when a call's status changes (e.g., started, ended).
    Extracts and persists the control URL when available.

    Args:
        message_data: The message data from the request
        session: The database session

    Returns:
        dict: Response for VAPI
    """
    try:
        status = message_data.get("status")
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        # Warn if call_id is missing (less critical for status updates)
        if not call_id or not isinstance(call_id, str) or not call_id.strip():
            logger.warning(
                "[handle_status_update] Invalid or missing call_id",
                extra={"call_data": call_data, "status": status},
            )

        logger.debug(
            f"Call {call_id} status updated to: {status}",
            extra={
                "call_id": call_id,
                "status": status,
            },
        )

        # Extract control URL from monitor data if available
        # Use `or {}` because .get() returns None if key exists with None value
        monitor_data = call_data.get("monitor") or {}
        control_url = monitor_data.get("controlUrl")

        # Store control URL using call_id to find the conversation
        # The conversation is created with call_id during handle_assistant_request
        if control_url and call_id:
            logger.debug(
                "[handle_status_update] Storing monitor control URL",
                extra={
                    "call_id": call_id,
                    "status": status,
                    "has_control_url": bool(control_url),
                },
            )
            conversation_repo = db.ConversationRepositoryAsync(session)
            conversation = await conversation_repo.get_conversation_by_call_id(call_id)

            if conversation:
                await conversation_repo.update_conversation(
                    conversation_id=conversation.id,
                    update_data=ConversationUpdate(
                        vapi_control_url=control_url,
                    ),
                )
                logger.debug(
                    "[handle_status_update] Stored control URL for conversation",
                    extra={
                        "call_id": call_id,
                        "conversation_id": str(conversation.id),
                        "status": status,
                    },
                )
            else:
                logger.error(
                    "[handle_status_update] No conversation found for call_id - control URL not stored",
                    extra={
                        "call_id": call_id,
                        "status": status,
                        "has_control_url": bool(control_url),
                    },
                )
        else:
            logger.debug(
                "[handle_status_update] No control URL or call_id available",
                extra={
                    "call_id": call_id,
                    "status": status,
                    "has_control_url": bool(control_url),
                },
            )

        # Acknowledge status updates
        return {"status": "acknowledged"}
    except Exception as e:
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")
        logger.error(
            "[handle_status_update] Error processing status update",
            extra={
                "call_id": call_id,
                "error": str(e),
            },
            exc_info=True,
        )
        return {"error": str(e)}


def handle_function_call(message_data):
    """
    Handle function-call message type.
    This is sent when the Assistant wants to call a function.

    Args:
        message_data: The message data from the request

    Returns:
        dict: Response for VAPI
    """
    try:
        function_call = message_data.get("functionCall", {})
        function_name = function_call.get("name")
        function_args = function_call.get("arguments", {})
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        logger.debug(
            f"Function call received for call {call_id}: {function_name} with args: {json.dumps(function_args)}"
        )

        # Handle different function types
        if function_name == "record_message":
            return handle_record_message(function_args, call_data, message_data)
        else:
            # Unknown function
            logger.warning(f"Unknown function call: {function_name}")
            return {
                "type": "function-call-response",
                "functionCall": {
                    "name": function_name,
                    "response": {"error": f"Unknown function: {function_name}"},
                },
            }
    except Exception as e:
        logger.error(f"Error in handle_function_call: {str(e)}")
        return {"error": str(e)}


def handle_tool_calls(message_data):
    """
    Handle tool-calls message type.
    This is sent when the Assistant wants to call a tool.

    Args:
        message_data: The message data from the request

    Returns:
        dict: A list of tool call results. Put error message in `error` field if any error occurs.
    """
    try:
        tool_calls = message_data.get("toolCallList", [])
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")
        logger.debug(
            f"Tool calls received for call {call_id}: {json.dumps(tool_calls)}"
        )

        # Handle different tool types
        results = []
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            tool_function = tool_call.get("function")
            tool_name = tool_function.get("name")
            tool_args = tool_function.get("arguments", {})
            logger.debug(
                f"Tool call received: {tool_name} with args: {json.dumps(tool_args)}"
            )
            results.append(
                {
                    "name": tool_name,
                    "toolCallId": tool_call_id,
                    "result": "<placeholder>",
                }
            )

        return {"results": results}

    except Exception as e:
        logger.error(f"Error in handle_tool_calls: {str(e)}")
        return {"error": str(e)}


def handle_record_message(args, call_data, message_data):
    """
    Handle the record_message function call.

    Args:
        args: The function arguments
        call_data: Information about the call
        message_data: The full message data

    Returns:
        dict: Response for VAPI
    """
    try:
        # Extract message details
        caller_name = args.get("caller_name", "Unknown")
        message_content = args.get("message", "")
        callback_number = args.get("callback_number", "")

        # Use the caller's number from the call data if callback_number wasn't provided
        if not callback_number:
            customer_data = message_data.get("customer", {})
            callback_number = customer_data.get("number", "Unknown")

        # Extract business information
        phone_number_data = message_data.get("phoneNumber", {})
        phone_number_name = phone_number_data.get("name", "")
        business_name = "default"
        if phone_number_name and ":" in phone_number_name:
            business_name = phone_number_name.split(":", 1)[1]

        # Log the message (in a real implementation, you'd store this in a database)
        logger.debug(
            f"Message recorded for {business_name}: Name: {caller_name}, Message: {message_content}, Callback: {callback_number}"
        )

        # Return success response
        return {
            "type": "function-call-response",
            "functionCall": {
                "name": "record_message",
                "response": {
                    "success": True,
                    "message": "Message recorded successfully",
                    "reference_id": call_data.get("id", "unknown_call"),
                },
            },
        }
    except Exception as e:
        logger.error(f"Error recording message: {str(e)}")
        return {
            "type": "function-call-response",
            "functionCall": {
                "name": "record_message",
                "response": {"success": False, "error": str(e)},
            },
        }


def handle_transcript_update(message_data):
    """
    Handle transcript-update message type.
    This is sent when new transcripts are available.

    Args:
        message_data: The message data from the request

    Returns:
        dict: Response for VAPI
    """
    try:
        transcript = message_data.get("transcript", {})
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        logger.debug(f"Transcript update for call {call_id}: {transcript}")

        # Just acknowledge transcript updates
        return {"status": "acknowledged"}
    except Exception as e:
        logger.error(f"Error in handle_transcript_update: {str(e)}")
        return {"error": str(e)}


async def _track_call_usage(
    call_data: dict,
    message_data: dict,
    project: db.Project,
    call_id: str,
) -> None:
    """
    Track call usage for billing.

    Args:
        call_data: Call data from VAPI end-of-call-report
        message_data: Message data from VAPI end-of-call-report (unused, for compatibility)
        project: Project object
        call_id: Call ID
    """
    try:
        # Track usage for all calls
        stripe_customer_id = project.account.stripe_customer_id

        if not stripe_customer_id:
            logger.info(
                f"No Stripe customer ID found for project {project.id} - skipping call usage tracking",
                extra={
                    "project_id": str(project.id),
                    "call_id": call_id,
                },
            )
            return

        event_name = _stripe_product.get_call_meter_event_name(project.id)

        await asyncio.to_thread(
            send_meter_event,
            event_name=event_name,
            stripe_customer_id=stripe_customer_id,
            value=1,
        )

        logger.info(
            "Successfully tracked call usage",
            extra={
                "call_id": call_id,
                "project_id": str(project.id),
            },
        )

    except Exception as e:
        logger.error(
            f"Error tracking call usage for call {call_id}: {e}",
            extra={"call_id": call_id, "project_id": str(project.id)},
            exc_info=True,
        )


async def handle_session_closure(message_data, session: AsyncSession):
    """
    Handle end-of-call-report message type.
    This is sent when a call has ended and the conversation should be closed.

    Args:
        message_data: The message data from the request

    Returns:
        dict: Response for VAPI
    """
    try:
        # Extract call information
        call_data = message_data.get("call", {})
        call_id = call_data.get("id")

        # Validate call_id is present and non-empty
        if not call_id or not isinstance(call_id, str) or not call_id.strip():
            logger.error(
                "[handle_session_closure] Invalid or missing call_id",
                extra={"call_data": call_data},
            )
            return {"error": "Invalid or missing call_id"}

        # TEMPORARY: Log to check for transcript in artifact (per VAPI docs)
        artifact = message_data.get("artifact", {})
        transcript_from_artifact = artifact.get("transcript", "") if artifact else ""

        logger.info(
            "[TEMP] VAPI end-of-call-report - checking for transcript in artifact",
            extra={
                "call_id": call_id,
                "has_artifact": "artifact" in message_data,
                "artifact_keys": list(artifact.keys()) if artifact else None,
                "has_transcript_in_artifact": (
                    "transcript" in artifact if artifact else False
                ),
                "transcript_length": (
                    len(transcript_from_artifact) if transcript_from_artifact else 0
                ),
                "transcript_preview": (
                    transcript_from_artifact[:200] + "..."
                    if transcript_from_artifact
                    else "No transcript found"
                ),
                "has_messages": "messages" in artifact if artifact else False,
                "messages_count": len(artifact.get("messages", [])) if artifact else 0,
            },
        )

        # this is for deleting the temporary assistant from the admin console self-onboarding
        metadata = message_data.get("assistant", {}).get("metadata", {})
        if (
            call_data.get("type") == "webCall"
            and (call_data.get("assistantId") or call_data.get("squadId"))
            and metadata.get("source") == "admin-console"
        ):
            assistant_type = metadata.get("type", {})
            if assistant_type == "multilingual_squad":
                assistant_ids = metadata.get("assistant_ids", [])
                try:
                    for assistant_id in assistant_ids:
                        logger.info(
                            f"Self-onboarding: assistant {assistant_id} started to be deleted"
                        )
                        await handle_delete_vapi_assistant(assistant_id)
                    await handle_delete_vapi_squad(call_data.get("squadId"))

                except Exception as e:
                    logger.error(
                        f"Self-onboarding: failed to delete squad {assistant_ids}: {e}"
                    )

            elif assistant_type == "single_assistant":
                assistant_id = call_data.get("assistantId")
                try:
                    logger.info(
                        f"Self-onboarding: assistant {assistant_id} started to be deleted"
                    )
                    await handle_delete_vapi_assistant(assistant_id)
                except Exception as e:
                    logger.error(
                        f"Self-onboarding: failed to delete assistant {assistant_id}: {e}"
                    )

        # Extract caller information
        customer_data = message_data.get("customer", {})
        customer_number = customer_data.get("number", "")

        # Extract business information
        phone_number_data = message_data.get("phoneNumber", {})
        phone_number = phone_number_data.get("number", "")

        logger.debug(
            f"Session closure request for call {call_id} from {customer_number} to {phone_number}"
        )

        # Find the conversation by caller information and update its status
        channel_identifier = f"voice:{customer_number}"
        project_channel_identifier = f"voice:{phone_number}"

        project_repo = db.ProjectRepositoryAsync(session)
        project = await project_repo.get_project_by_channel_identifier(
            project_channel_identifier
        )
        if not project:
            raise ValueError(
                f"Project not found for this message: {project_channel_identifier}"
            )

        user = await user_service.get_user_by_channel_identifier_async(
            session=session,
            account_id=project.account_id,
            channel_identifier=channel_identifier,
        )
        if not user:
            raise ValueError(
                f"User not found for this message: account_id: {project.account_id}, channel_identifier:{channel_identifier}"
            )

        conversation_repo = db.ConversationRepositoryAsync(session)
        conversations = (
            await conversation_repo.get_open_conversations_by_user_and_project(
                user.id, project.id
            )
        )

        if not conversations:
            logger.warning(f"No matching active conversation found for call {call_id}")
        else:
            if len(conversations) > 1:
                logger.warning(
                    f"There are {len(conversations)} open conversations exist for user: {user.id}"
                )
            for conversation in conversations:
                conversation.status = db.ConversationStatus.CLOSING

            # Save phone call data to the first conversation, in most of the cases, there is only one conversation,
            # We do not need to create a duplicated call with different conversations
            first_conversation = conversations[0]
            if call_id:
                try:
                    phone_call = await message_service.create_phone_call_record(
                        session=session,
                        message=message_data,
                        call_id=call_id,
                        conversation_id=first_conversation.id,
                    )
                    logger.info(
                        f"[phone_call] Phone call data saved: {phone_call.id} for conversation {first_conversation.id}"
                    )
                except Exception as e:
                    logger.error(f"[phone_call] Failed to save phone call data: {e}")

                try:
                    conversation_data = transform_vapi_conversation_data(message_data)
                    await conversation_repo.update_conversation(
                        conversation_id=first_conversation.id,
                        update_data=ConversationUpdate(**conversation_data),
                    )
                    logger.info(
                        f"[conversation] Updated conversation {first_conversation.id} with Vapi data: {conversation_data}"
                    )
                except Exception as e:
                    logger.error(
                        f"[conversation] Failed to update conversation with Vapi data: {e}"
                    )

            await session.commit()

        # Refresh project after commit to avoid MissingGreenlet error
        # when accessing project.account in _track_call_usage
        await session.refresh(project, attribute_names=["account"])

        # Measure and record voice-to-voice latency metrics
        await _measure_voice_to_voice_latency(message_data)

        # Send webhook on hangup asynchronously if the business number is allowlisted
        webhook_url, webhook_secret, allowed_numbers = _get_webhook_config()
        if (
            webhook_url
            and webhook_secret
            and _is_allowed_business_number(phone_number, allowed_numbers)
        ):
            # Extract transcript from artifact (per VAPI docs structure)
            transcript_text = artifact.get("transcript", "") if artifact else ""

            # TEMPORARY: Log transcript extraction
            logger.info(
                "[TEMP] Extracting transcript for webhook",
                extra={
                    "call_id": call_id,
                    "transcript_found": bool(transcript_text),
                    "transcript_length": len(transcript_text) if transcript_text else 0,
                },
            )
            payload = {
                "call_id": call_id,
                "business_number": phone_number,
                "caller_number": customer_number,
                "ended_reason": call_data.get("endedReason"),
                "duration_seconds": call_data.get("durationSeconds"),
                "transcript": transcript_text,
            }
            # Log without PII; include only last 4 of numbers
            masked_business = phone_number[-4:] if phone_number else ""
            masked_caller = customer_number[-4:] if customer_number else ""
            # Schedule background task to avoid blocking the request path
            import asyncio as _asyncio

            _asyncio.create_task(
                _send_hangup_webhook_background(
                    payload=payload,
                    business_last4=masked_business,
                    caller_last4=masked_caller,
                )
            )
        else:
            # Log why the webhook was skipped
            masked_business = phone_number[-4:] if phone_number else ""
            masked_caller = customer_number[-4:] if customer_number else ""
            if not webhook_url:
                reason = "missing_webhook_url"
            elif not webhook_secret:
                reason = "missing_bearer_token"
            elif not _is_allowed_business_number(phone_number, allowed_numbers):
                reason = "business_number_not_allowlisted"
            else:
                reason = "unknown"
            logger.info(
                "Hangup webhook skipped",
                extra={
                    "call_id": call_id,
                    "reason": reason,
                    "business_last4": masked_business,
                    "caller_last4": masked_caller,
                    "allowlist_size": len(allowed_numbers),
                },
            )

        # Track usage for all calls
        await _track_call_usage(
            call_data=call_data,
            message_data=message_data,
            project=project,
            call_id=call_id,
        )

        return {
            "status": "session closed",
        }

    except Exception as e:
        logger.error(f"Error in handle_session_closure: {str(e)}")
        return {"error": str(e)}


async def handle_create_vapi_assistant(
    create_request,
) -> str:
    """Create a new VAPI assistant or squad using the server SDK."""

    vapi_client = _get_vapi_client()
    logger.info(f"Creating VAPI assistant for {create_request.name}")

    # For Multilingual: create a squad instead of a single assistant
    if create_request.language == "Multilingual":
        logger.info(f"Creating multilingual squad for {create_request.name}")

        # Step 1: Create all assistant members first
        triage_config, english_config, spanish_config, chinese_config = (
            _build_multilingual_squad(create_request)
        )

        # Create assistants
        triage = await vapi_client.assistants.create(**triage_config)
        english = await vapi_client.assistants.create(**english_config)
        spanish = await vapi_client.assistants.create(**spanish_config)
        chinese = await vapi_client.assistants.create(**chinese_config)

        logger.info(
            f"Created assistants: triage={triage.id} ({triage.name}), english={english.id} ({english.name}), spanish={spanish.id} ({spanish.name}), chinese={chinese.id} ({chinese.name})"
        )

        # Step 2: Create squad with assistant IDs and routing configuration
        squad_data = {
            "name": create_request.name,
            "members": [
                {
                    "assistant_id": triage.id,
                    "assistant_destinations": [
                        {
                            "type": "assistant",
                            "assistant_name": english.name,
                            "message": "Transferring you to our English specialist...",
                            "description": "Transfer to English language assistant",
                            "transfer_mode": "rolling-history",
                        },
                        {
                            "type": "assistant",
                            "assistant_name": spanish.name,
                            "message": "¡Está bien, no hay problema!",
                            "description": "Transfer to Spanish language assistant",
                            "transfer_mode": "rolling-history",
                        },
                        {
                            "type": "assistant",
                            "assistant_name": chinese.name,
                            "message": "好的，没问题！",
                            "description": "Transfer to Chinese language assistant",
                            "transfer_mode": "rolling-history",
                        },
                    ],
                },
                {"assistant_id": english.id},
                {"assistant_id": spanish.id},
                {"assistant_id": chinese.id},
            ],
            "members_overrides": {
                "metadata": {
                    "source": "admin-console",
                    "type": "multilingual_squad",
                    "assistant_ids": [triage.id, english.id, spanish.id, chinese.id],
                }
            },
        }
        squad = await vapi_client.squads.create(**squad_data)
        logger.info(f"Successfully created VAPI squad: {squad.id}")
        return squad.id

    # For single language: create a single assistant
    assistant_data = _build_assistant(create_request)
    assistant = await vapi_client.assistants.create(**assistant_data)
    logger.info(f"Successfully created VAPI assistant: {assistant.id}")
    return assistant.id


def _build_multilingual_squad(create_request) -> tuple[dict, dict, dict, dict]:
    """Build multilingual squad configuration with triage and language assistants.

    System Prompt Assignment:
    - English: Uses create_request.systemPrompt directly
    - Spanish: Prepends language enforcement rules + create_request.systemPrompt
    - Chinese: Prepends language enforcement rules + create_request.systemPrompt

    First Message (Language-Specific):
    - English: "Hello! How can I help you today?"
    - Spanish: "¡Hola! ¿Cómo puedo ayudarte hoy?"
    - Chinese: "你好！我今天能帮你什么？"

    This ensures each language assistant greets in the appropriate language
    and has the full system instructions from create_request.

    Returns:
        tuple: (triage_config, english_config, spanish_config, chinese_config)
    """
    # Language configuration for each supported language
    # Each assistant will receive: system_prefix + create_request.systemPrompt
    languages = {
        "english": {
            "display": "English",
            "transcriber_code": "en",
            "system_prefix": "",  # No prefix, uses systemPrompt as-is
            "first_message": "Hello! How can I help you today?",
        },
        "spanish": {
            "display": "Spanish",
            "transcriber_code": "es",
            "system_prefix": "=== REGLA CRÍTICA DE IDIOMA ===\nDEBES responder SIEMPRE y ÚNICAMENTE en ESPAÑOL. \n\n",
            "first_message": "¡Hola! ¿Cómo puedo ayudarte hoy?",
        },
        "chinese": {
            "display": "Chinese",
            "transcriber_code": "zh",
            "system_prefix": "=== 关键语言规则 ===\n你必须始终只用中文回复。请用中文回复数字 比如念时间的时候用中文回复 “1234” 是 “一二三四”。\n\n",
            "first_message": "你好！我今天能帮你什么？",
        },
    }

    # Build triage assistant
    triage = _build_squad_triage_assistant(create_request, languages)

    # Build language-specific assistants
    assistants = {
        lang: _build_squad_language_assistant(create_request, lang, config)
        for lang, config in languages.items()
    }

    return triage, assistants["english"], assistants["spanish"], assistants["chinese"]


def _build_squad_triage_assistant(create_request, languages: dict) -> dict:
    """Build triage assistant for multilingual squad."""
    triage_name = _format_assistant_name(create_request.name, " (Language Triage)")

    # Build transfer instructions dynamically
    transfer_rules = [
        f"- For {config['display']} → transfer to {_format_assistant_name(create_request.name, config['display'])}"
        for config in languages.values()
    ]

    system_prompt = f"""You are the initial language detection assistant.

Your ONLY responsibility is to:
1. Greet the customer warmly
2. Identify their preferred language (English, Spanish, or Chinese)
3. Transfer them to the appropriate language specialist immediately

Say: "Hello! I can help you in English, español, or 中文. Which language would you prefer?"

IMPORTANT: As soon as you detect the language, transfer immediately to the appropriate assistant:
{chr(10).join(transfer_rules)}

DO NOT attempt to help with their actual request."""

    return {
        "name": triage_name,
        "transcriber": {
            "provider": "google",
            "model": "gemini-2.5-flash",
            "language": "Multilingual",
        },
        "model": _build_squad_model_config(0.3, system_prompt),
        "voice": _build_squad_voice_config(create_request.voiceId),
        "first_message": create_request.firstMessage
        or "Hello! I can help you in English, español, or 中文. Which language would you prefer?",
        "metadata": {
            "source": "admin-console",
            "type": "squad_member",
            "role": "triage",
        },
    }


def _build_squad_language_assistant(
    create_request, language: str, config: dict
) -> dict:
    """Build language-specific assistant for multilingual squad.

    Each language assistant receives:
    - The base system prompt from create_request.systemPrompt
    - A language-specific prefix (if applicable) to enforce language use
    - A first message in the appropriate language
    """

    assistant_name = _format_assistant_name(create_request.name, config["display"])

    # Combine language-specific prefix with the base system prompt
    # This ensures each assistant has the full system instructions
    system_content = config["system_prefix"] + create_request.systemPrompt

    logger.debug(
        f"Building {language} assistant with system prompt (length: {len(system_content)} chars)"
    )

    return {
        "name": assistant_name,
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": config["transcriber_code"],
        },
        "model": _build_squad_model_config(0.3, system_content),
        "voice": _build_squad_voice_config(create_request.voiceId),
        "first_message": config["first_message"],
        "metadata": {
            "source": "admin-console",
            "type": "squad_member",
            "role": "language",
            "language": language,
        },
    }


def _build_squad_model_config(temperature: float, system_content: str) -> dict:
    """Build model configuration for squad assistants."""
    return {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": temperature,
        "messages": [{"role": "system", "content": system_content}],
    }


def _build_squad_voice_config(voice_id: str) -> dict:
    """Build voice configuration for squad assistants."""
    return {
        "provider": "cartesia",
        "model": "sonic-2",
        "voice_id": voice_id,
    }


def _build_assistant(create_request) -> dict:
    """Build assistant configuration."""
    language = create_request.language

    # Base assistant configuration
    assistant_data = {
        "name": create_request.name,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
            "messages": [
                {
                    "role": "system",
                    "content": create_request.systemPrompt,
                }
            ],
        },
        "voice": {
            "provider": "cartesia",
            "model": "sonic-2",
            "voice_id": create_request.voiceId,
        },
        "metadata": {
            "source": "admin-console",
            "type": "single_assistant",
            "language": language.lower() if language else "english",
        },
    }

    # Add optional configurable fields with correct snake_case names
    if create_request.firstMessage is not None:
        assistant_data["first_message"] = create_request.firstMessage
    if create_request.maxDurationSeconds is not None:
        assistant_data["max_duration_seconds"] = create_request.maxDurationSeconds

    # For English: use standard Deepgram transcriber
    if language == "English":
        return assistant_data

    # For Spanish and Chinese: add language-specific transcriber configurations
    language_settings = {
        "Spanish": {
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "es",
            },
            "language_instruction": "\n\n=== REGLA CRÍTICA DE IDIOMA ===\nDEBES responder SIEMPRE y ÚNICAMENTE en ESPAÑOL.\nNUNCA uses inglés u otro idioma.\nToda tu conversación debe ser 100% en español.\nMantén una conversación natural con el usuario.\nNo termines la llamada a menos que el usuario lo pida explícitamente.",
        },
        "Chinese": {
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "zh-CN",
            },
            "language_instruction": "\n\n=== 关键语言规则 ===\n你必须始终只用中文回复。\n绝对不要使用英语或其他语言。\n你的整个对话必须100%用中文。\n与用户进行自然对话。\n除非用户明确要求，否则不要结束通话.",
        },
    }

    if language in language_settings:
        settings = language_settings[language]

        # Add transcriber configuration
        assistant_data["transcriber"] = settings["transcriber"]

        # Prepend language instruction to system prompt (at the beginning for maximum prominence)
        assistant_data["model"]["messages"][0]["content"] = (
            settings["language_instruction"] + "\n\n" + create_request.systemPrompt
        )

    return assistant_data


async def handle_delete_vapi_assistant(assistant_id: str):
    """Delete a VAPI assistant or squad.

    Metadata helps identify what type of assistant is being deleted:
    - single_assistant: A standalone assistant (delete only this assistant)
    - squad_member: Part of a squad (may need to delete entire squad)
    """

    vapi_client = _get_vapi_client()

    # Delete assistant via VAPI API - let exceptions propagate
    await vapi_client.assistants.delete(assistant_id)

    logger.info(f"Successfully deleted VAPI assistant: {assistant_id}")
    return


async def handle_delete_vapi_squad(squad_id: str):
    """Delete a VAPI squad."""
    vapi_client = _get_vapi_client()
    await vapi_client.squads.delete(squad_id)
    logger.info(f"Successfully deleted VAPI squad: {squad_id}")
    return
