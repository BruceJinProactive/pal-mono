import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from dateutil import parser as date_parser
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
from utils.secret import get_server_secret_with_fallback


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
    logger.debug(
        f"[VAPI DEBUG] Retrieving logs for call {call_id} to measure voice-to-voice latency"
    )
    try:
        logger.debug("[VAPI DEBUG] Starting log retrieval for call")
        logs_pager = await vapi_client.logs.get(call_id=call_id, type="Call")

        # Collect and filter logs from the pager
        log_count = 0
        async for log in logs_pager:
            log_count += 1
            # Filter for turn latency logs
            log_level = getattr(log, "level", None)
            log_message = getattr(log, "log", None)
            logger.debug(
                f"[VAPI DEBUG] Log #{log_count} for call {call_id}: level={log_level}, message={log_message[:100] if log_message else None}"
            )
            if log_level == "INFO" and log_message and "Turn latency:" in log_message:
                logger.debug(
                    f"[VAPI DEBUG] Processing log for call {call_id}: {log_message}"
                )
                send_dd_latency(log_message, call_id, customer_number, phone_number)

        logger.debug(
            f"[VAPI DEBUG] Finished processing {log_count} logs for call {call_id}"
        )

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
            # Transfer settings for VAPI transferCall tool configuration
            "transfer_phone_number": project.transfer_phone_number,
            "transfer_message": project.transfer_message,
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


def _is_test_phone_number(phone_number: str) -> bool:
    """
    Check if a phone number is a Palona test/internal number.

    Reads from AWS Secrets Manager or environment variable TEST_PHONE_NUMBERS
    which should be a comma-separated list of phone numbers.

    Example: TEST_PHONE_NUMBERS="+18889738742,+18885551234,+12125551212"

    Args:
        phone_number: Phone number to check

    Returns:
        bool: True if test number, False otherwise
    """
    try:
        # Get test phone numbers from AWS Secrets Manager with env fallback
        test_numbers_str = get_server_secret_with_fallback("TEST_PHONE_NUMBERS")
    except (ValueError, KeyError):
        # Secret not found, no test numbers configured
        return False

    if not test_numbers_str:
        return False

    # Parse comma-separated phone numbers and strip whitespace
    test_numbers = {num.strip() for num in test_numbers_str.split(",") if num.strip()}

    return phone_number in test_numbers


def _should_track_call_usage(
    message_data: dict,
    customer_number: str,
) -> tuple[bool, str]:
    """
    Determine if a call should be tracked for billing based on filtering rules.

    Filtering rules:
    1. Exclude test phone numbers (Palona internal)
    2. Exclude calls where customer didn't speak
    3. Exclude calls less than 10 seconds in duration

    Args:
        call_data: Call data from VAPI
        message_data: Message data from VAPI
        customer_number: Customer phone number
        call_id: Call ID
        conversation_start_time: Conversation created_at timestamp from database (unused for now)

    Returns:
        tuple: (should_track: bool, skip_reason: str)
    """
    # Rule 1: Check if test phone number
    if _is_test_phone_number(customer_number):
        return False, f"test_number:{customer_number}"

    # Rule 2: Check call duration using message.startedAt and message.endedAt
    # If call is less than 10 seconds, don't count as usage
    call_data = message_data.get("call", {})
    started_at = message_data.get("startedAt")
    ended_at = message_data.get("endedAt")

    if started_at and ended_at:
        try:
            # Parse ISO timestamps and calculate duration in seconds
            start_time = date_parser.isoparse(started_at)
            end_time = date_parser.isoparse(ended_at)
            duration_seconds = (end_time - start_time).total_seconds()

            if duration_seconds < 10:
                return False, f"call_too_short:{duration_seconds:.2f}s"
        except Exception as e:
            logger.info(
                f"Failed to parse call timestamps: {e}",
                extra={
                    "call_id": call_data.get("id"),
                    "started_at": started_at,
                    "ended_at": ended_at,
                },
            )
            # Continue with other checks if timestamp parsing fails

    # Rule 3: Check if customer spoke
    artifact = message_data.get("artifact", {})
    messages = artifact.get("messages", [])

    customer_spoke = False
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "").lower()
            if role == "user":
                # Check if message has content
                if msg.get("message") or msg.get("content"):
                    customer_spoke = True
                    break

    if not customer_spoke:
        return False, "customer_did_not_speak"

    # All checks passed
    return True, ""


async def _track_call_usage(
    message_data: dict,
    project: db.Project,
    call_id: str,
) -> None:
    """
    Track call usage for billing with filtering rules.

    Filters out:
    - Test phone numbers (Palona internal)
    - Calls where customer didn't speak

    Args:
        call_data: Call data from VAPI end-of-call-report
        message_data: Message data from VAPI end-of-call-report
        project: Project object
        call_id: Call ID
        conversation: Conversation object for start time
    """
    try:
        # Extract customer number for filtering
        customer_data = message_data.get("customer", {})
        customer_number = customer_data.get("number", "")

        # Check if call should be tracked based on filtering rules
        should_track, skip_reason = _should_track_call_usage(
            message_data, customer_number
        )

        if not should_track:
            logger.info(
                f"Skipping call usage tracking for call {call_id}: {skip_reason}",
                extra={
                    "call_id": call_id,
                    "project_id": str(project.id),
                    "skip_reason": skip_reason,
                    "customer_number": customer_number[-4:] if customer_number else "",
                },
            )
            return

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

        first_conversation = None
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
            transcript_text = (
                message_data.get("transcript") or call_data.get("transcript") or ""
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
) -> dict[str, str | None]:
    """Create a new VAPI assistant or squad using the server SDK.

    Interprets languageGroups to determine what to create:
    - Single group with single language: single-language assistant
    - Single group with multiple languages: single multilingual assistant
    - Multiple groups: squad with triage + one assistant per group

    Returns:
        dict: {"assistantId": str, "squadId": None} for single assistant
              {"assistantId": None, "squadId": str} for squad
    """
    vapi_client = _get_vapi_client()
    language_groups = create_request.languageGroups

    logger.debug(
        f"[handle_create_vapi_assistant] Creating VAPI assistant for {create_request.name} with language groups: {language_groups}"
    )

    # Validate language groups
    if not language_groups or len(language_groups) == 0:
        raise ValueError("languageGroups must contain at least one group")

    for group in language_groups:
        if not group or len(group) == 0:
            raise ValueError("Each language group must contain at least one language")
        for language in group:
            if not isinstance(language, str) or not language.strip():
                raise ValueError("Each language must be a non-empty string")

    # Validate transcribers array if provided
    transcribers = create_request.transcribers
    if transcribers is not None:
        if len(transcribers) != len(language_groups):
            raise ValueError(
                f"transcribers length ({len(transcribers)}) must match "
                f"languageGroups length ({len(language_groups)})"
            )

    # Case 1: Single group - create a single assistant (possibly multilingual)
    if len(language_groups) == 1:
        languages_in_group = language_groups[0]
        transcriber = transcribers[0] if transcribers else None
        assistant_data = _build_single_assistant(
            create_request, languages_in_group, transcriber
        )
        assistant = await vapi_client.assistants.create(**assistant_data)
        logger.debug(
            f"[handle_create_vapi_assistant] Successfully created VAPI assistant: {assistant.id} for languages: {languages_in_group}"
        )
        return {"assistantId": assistant.id, "squadId": None}

    # Case 2: Multiple groups - create a squad with triage
    logger.debug(
        f"[handle_create_vapi_assistant] Creating squad for {create_request.name} with {len(language_groups)} language groups"
    )

    # Build triage and group assistants
    triage_config = _build_dynamic_triage_assistant(create_request, language_groups)
    group_configs = [
        _build_group_assistant(
            create_request,
            group,
            idx,
            transcribers[idx] if transcribers else None,
        )
        for idx, group in enumerate(language_groups)
    ]

    # Create all assistants with cleanup on failure
    created_assistants: list = []
    try:
        triage = await vapi_client.assistants.create(**triage_config)
        created_assistants.append(triage)
        group_assistants = []
        for config in group_configs:
            assistant = await vapi_client.assistants.create(**config)
            created_assistants.append(assistant)
            group_assistants.append(assistant)

        logger.debug(
            f"[handle_create_vapi_assistant] Created triage assistant: {triage.id} ({triage.name}) and "
            f"{len(group_assistants)} group assistants"
        )

        # Build squad with routing
        squad_data = _build_squad_data(
            create_request, triage, group_assistants, language_groups
        )
        squad = await vapi_client.squads.create(**squad_data)
        logger.debug(
            f"[handle_create_vapi_assistant] Successfully created VAPI squad: {squad.id}"
        )
        return {"assistantId": None, "squadId": squad.id}
    except Exception:
        # Cleanup any created assistants on failure to avoid orphans
        for assistant in created_assistants:
            try:
                await vapi_client.assistants.delete(assistant.id)
                logger.debug(
                    f"[handle_create_vapi_assistant] Cleaned up orphaned assistant: {assistant.id}"
                )
            except Exception as cleanup_error:
                logger.warning(
                    f"[handle_create_vapi_assistant] Failed to cleanup orphaned assistant {assistant.id}: {cleanup_error}"
                )
        raise


# Language configuration for supported languages
LANGUAGE_CONFIG: dict[str, dict[str, str]] = {
    "English": {
        "display": "English",
        "transcriber_code": "en",
        "system_prefix": "",
        "first_message": "Hello! How can I help you today?",
        "transfer_message": "Transferring you to our English specialist...",
    },
    "Spanish": {
        "display": "Spanish",
        "transcriber_code": "es",
        "system_prefix": "=== REGLA CRÍTICA DE IDIOMA ===\nDEBES responder SIEMPRE y ÚNICAMENTE en ESPAÑOL.\n\n",
        "first_message": "¡Hola! ¿Cómo puedo ayudarte hoy?",
        "transfer_message": "¡Está bien, no hay problema!",
    },
    "Chinese": {
        "display": "Chinese",
        "transcriber_code": "zh",
        "system_prefix": '=== 关键语言规则 ===\n你必须始终只用中文回复。请用中文回复数字 比如念时间的时候用中文回复 "1234" 是 "一二三四"。\n\n',
        "first_message": "你好！我今天能帮你什么？",
        "transfer_message": "好的，没问题！",
    },
}


def _get_language_config(language: str) -> dict[str, str]:
    """Get configuration for a language, with fallback to English-like defaults."""
    normalized = language.strip().title()
    if normalized in LANGUAGE_CONFIG:
        return LANGUAGE_CONFIG[normalized]
    # Fallback for unknown languages
    return {
        "display": normalized,
        "transcriber_code": "en",
        "system_prefix": "",
        "first_message": "Hello! How can I help you today?",
        "transfer_message": f"Transferring you to our {normalized} specialist...",
    }


def _build_single_assistant(
    create_request, languages: list[str], transcriber: dict | None = None
) -> dict:
    """Build a single assistant configuration for one or more languages.

    Args:
        create_request: The assistant creation request
        languages: List of languages this assistant should support
        transcriber: Optional transcriber config for this assistant

    Returns:
        dict: Assistant configuration for VAPI
    """
    is_multilingual = len(languages) > 1

    # For single-language assistants, prepend language-specific system prefix
    # For multilingual assistants, use systemPrompt as-is (no language enforcement)
    primary_config = _get_language_config(languages[0])
    system_content = (
        f"{primary_config['system_prefix']}{create_request.systemPrompt}"
        if not is_multilingual
        else create_request.systemPrompt
    )

    # Base assistant configuration
    assistant_data: dict[str, Any] = {
        "name": create_request.name,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
            "messages": [{"role": "system", "content": system_content}],
        },
        "voice": {
            "provider": create_request.voice.provider,
            "model": create_request.voice.model,
            "voiceId": create_request.voice.voiceId,
        },
        "metadata": {
            "source": "admin-console",
            "type": "single_assistant",
            "languages": [lang.lower() for lang in languages],
            "is_multilingual": is_multilingual,
        },
    }

    # Add optional configurable fields
    if create_request.firstMessage is not None:
        assistant_data["first_message"] = create_request.firstMessage
    if create_request.maxDurationSeconds is not None:
        assistant_data["max_duration_seconds"] = create_request.maxDurationSeconds

    # Use transcriber config if provided, otherwise use default for English-only
    if transcriber:
        assistant_data["transcriber"] = transcriber
    else:
        # Check if any non-English languages are present
        has_non_english = any(lang.strip().lower() != "english" for lang in languages)
        if has_non_english:
            raise ValueError(
                "transcriber configuration is required for non-English language assistants"
            )
        # Default to Deepgram nova-3 with en-US for English-only assistants
        assistant_data["transcriber"] = {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "en-US",
        }

    return assistant_data


def _build_dynamic_triage_assistant(
    create_request, language_groups: list[list[str]]
) -> dict:
    """Build triage assistant for dynamic language groups.

    Args:
        create_request: The assistant creation request
        language_groups: List of language groups (each group becomes one assistant)

    Returns:
        dict: Triage assistant configuration
    """
    triage_name = _format_assistant_name(create_request.name, " (Language Triage)")

    # Build language options for greeting
    all_languages = []
    for group in language_groups:
        all_languages.extend(group)
    unique_languages = list(
        dict.fromkeys(all_languages)
    )  # Preserve order, remove dupes

    # Build greeting with available languages
    language_options = []
    for lang in unique_languages:
        config = _get_language_config(lang)
        if lang.lower() == "english":
            language_options.append("English")
        elif lang.lower() == "spanish":
            language_options.append("español")
        elif lang.lower() == "chinese":
            language_options.append("中文")
        else:
            language_options.append(config["display"])

    greeting_languages = (
        ", ".join(language_options[:-1]) + f", or {language_options[-1]}"
        if len(language_options) > 1
        else language_options[0]
    )

    # Build transfer rules for each group
    transfer_rules = []
    for idx, group in enumerate(language_groups):
        group_name = _get_group_display_name(group)
        assistant_name = _format_assistant_name(create_request.name, f" ({group_name})")
        languages_in_group = ", ".join(group)
        transfer_rules.append(
            f"- For {languages_in_group} → transfer to {assistant_name}"
        )

    system_prompt = f"""You are the initial language detection assistant.

Your ONLY responsibility is to:
1. Greet the customer warmly
2. Identify their preferred language
3. Transfer them to the appropriate language specialist immediately

Say: "Hello! I can help you in {greeting_languages}. Which language would you prefer?"

IMPORTANT: As soon as you detect the language, transfer immediately to the appropriate assistant:
{chr(10).join(transfer_rules)}

DO NOT attempt to help with their actual request."""

    default_greeting = f"Hello! I can help you in {greeting_languages}. Which language would you prefer?"

    # Build transcriber config based on languages (same logic as admin console)
    # Map language names to codes
    lang_code_map = {
        "english": "en",
        "spanish": "es",
        "chinese": "zh",
    }
    lang_codes = [
        lang_code_map.get(lang.lower(), lang.lower()) for lang in unique_languages
    ]

    # Determine transcriber config based on language combination
    has_english = "en" in lang_codes
    has_spanish = "es" in lang_codes
    only_english_spanish = len(lang_codes) == 2 and has_english and has_spanish

    if only_english_spanish:
        # English + Spanish only: use Nova-3 multi
        transcriber_config: dict[str, Any] = {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "multi",
        }
    else:
        # Other combinations: use Gladia with multiple languages
        transcriber_config = {
            "model": "solaria-1",
            "provider": "gladia",
            "languages": lang_codes,
            "languageBehaviour": "automatic multiple languages",
            "confidenceThreshold": 0.1,
            "receivePartialTranscripts": True,
        }

    return {
        "name": triage_name,
        "transcriber": transcriber_config,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
            "messages": [{"role": "system", "content": system_prompt}],
        },
        "voice": {
            "provider": create_request.voice.provider,
            "model": create_request.voice.model,
            "voiceId": create_request.voice.voiceId,
        },
        "first_message": create_request.firstMessage or default_greeting,
        "metadata": {
            "source": "admin-console",
            "type": "squad_member",
            "role": "triage",
            "language_groups": language_groups,
        },
    }


def _get_group_display_name(languages: list[str]) -> str:
    """Get a display name for a language group."""
    if len(languages) == 1:
        return _get_language_config(languages[0])["display"]
    return "+".join(_get_language_config(lang)["display"] for lang in languages)


def _build_group_assistant(
    create_request,
    languages: list[str],
    group_index: int,
    transcriber: dict | None = None,
) -> dict:
    """Build an assistant for a language group in a squad.

    Args:
        create_request: The assistant creation request
        languages: Languages this assistant handles
        group_index: Index of this group (for naming)
        transcriber: Optional transcriber config for this assistant

    Returns:
        dict: Assistant configuration for this language group
    """
    group_name = _get_group_display_name(languages)
    assistant_name = _format_assistant_name(create_request.name, f" ({group_name})")

    # Get first message based on primary language
    primary_config = _get_language_config(languages[0])
    first_message = primary_config["first_message"]

    # For single-language groups, prepend language-specific system prefix
    # For multilingual groups, use systemPrompt as-is (no language enforcement)
    system_content = (
        f"{primary_config['system_prefix']}{create_request.systemPrompt}"
        if len(languages) == 1
        else create_request.systemPrompt
    )

    assistant_data: dict[str, Any] = {
        "name": assistant_name,
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
            "messages": [{"role": "system", "content": system_content}],
        },
        "voice": {
            "provider": create_request.voice.provider,
            "model": create_request.voice.model,
            "voiceId": create_request.voice.voiceId,
        },
        "first_message": first_message,
        "metadata": {
            "source": "admin-console",
            "type": "squad_member",
            "role": "language",
            "languages": [lang.lower() for lang in languages],
            "group_index": group_index,
        },
    }

    # Use transcriber config if provided, otherwise use default for English-only
    if transcriber:
        assistant_data["transcriber"] = transcriber
    else:
        # Check if any non-English languages are present
        has_non_english = any(lang.strip().lower() != "english" for lang in languages)
        if has_non_english:
            raise ValueError(
                "transcriber configuration is required for non-English language assistants"
            )
        # Default to Deepgram nova-3 with en-US for English-only assistants
        assistant_data["transcriber"] = {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "en-US",
        }

    return assistant_data


def _build_squad_data(
    create_request,
    triage,
    group_assistants: list,
    language_groups: list[list[str]],
) -> dict:
    """Build squad configuration with triage and language group assistants.

    Args:
        create_request: The assistant creation request
        triage: The created triage assistant
        group_assistants: List of created group assistants
        language_groups: The original language groups

    Returns:
        dict: Squad configuration for VAPI
    """
    # Build assistant destinations for triage
    assistant_destinations = []
    for idx, (assistant, languages) in enumerate(
        zip(group_assistants, language_groups)
    ):
        primary_config = _get_language_config(languages[0])
        assistant_destinations.append(
            {
                "type": "assistant",
                "assistant_name": assistant.name,
                "message": primary_config["transfer_message"],
                "description": f"Transfer to {_get_group_display_name(languages)} assistant",
                "transfer_mode": "swap-system-message-in-history",
            }
        )

    # Build members list
    members = [
        {
            "assistant_id": triage.id,
            "assistant_destinations": assistant_destinations,
        }
    ]
    for assistant in group_assistants:
        members.append({"assistant_id": assistant.id})

    return {
        "name": create_request.name,
        "members": members,
        "members_overrides": {
            "metadata": {
                "source": "admin-console",
                "type": "multilingual_squad",
                "assistant_ids": [triage.id] + [a.id for a in group_assistants],
                "language_groups": language_groups,
            }
        },
    }


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
