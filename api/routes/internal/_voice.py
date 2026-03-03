"""Implementation for LiveKit voice call initialization endpoint."""

import asyncio
import uuid
from datetime import datetime, timezone

import pytz
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.chat.message import (
    AuthorType,
    Extras,
    Message,
    Metadata,
    TextObject,
    Type,
)
from api.schemas.internal.voice_init import (
    VoiceEndCallRequest,
    VoiceInitRequest,
    VoiceInitResponse,
)
from db.repositories.voice_config_repository import VoiceConfigRepositoryAsync
from db.tables.types import Channel, SpeechRate
from events import ConversationEvaluationRequested, publish_event
from services import project_service, subscription_service, user_service
from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Numeric speed mapping matching CARTESIA_SONIC3_SPEED_MAPPING from
# services/voice_service/providers/vapi/_implementation.py
_SPEECH_RATE_TO_FLOAT: dict[SpeechRate, float] = {
    SpeechRate.slowest: 0.6,
    SpeechRate.slower: 0.8,
    SpeechRate.normal: 1.0,
    SpeechRate.faster: 1.25,
    SpeechRate.fastest: 1.5,
}

# Default STT configuration per language
_STT_CONFIGS: dict[str, dict[str, str]] = {
    "english": {"model": "nova-3", "language": "en-US"},
    "spanish": {"model": "nova-2", "language": "es"},
    "chinese": {"model": "nova-2", "language": "zh-CN"},
}

# Time-based greetings per language
_TIMEZONE_GREETINGS: dict[str, dict[str, str]] = {
    "english": {
        "morning": "Good morning!",
        "afternoon": "Good afternoon!",
        "evening": "Good evening!",
    },
    "spanish": {
        "morning": "Buenos d\u00edas!",
        "afternoon": "Buenas tardes!",
        "evening": "Buenas noches!",
    },
    "chinese": {
        "morning": "\u65e9\u4e0a\u597d\uff01",
        "afternoon": "\u4e0b\u5348\u597d\uff01",
        "evening": "\u665a\u4e0a\u597d\uff01",
    },
}


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
    caller_number: str,
    duration_seconds: float,
    conversation_history: list[dict],
) -> tuple[bool, str]:
    """
    Determine if a call should be tracked for billing based on filtering rules.

    Filtering rules:
    1. Exclude test phone numbers (Palona internal)
    2. Exclude calls less than 10 seconds in duration
    3. Exclude calls where customer didn't speak

    Args:
        caller_number: Customer phone number
        duration_seconds: Call duration in seconds
        conversation_history: List of message dicts with 'role' and 'content'

    Returns:
        tuple: (should_track: bool, skip_reason: str)
    """
    # Rule 1: Check if test phone number
    if _is_test_phone_number(caller_number):
        return False, f"test_number:{caller_number}"

    # Rule 2: Check call duration
    # If call is less than 10 seconds, don't count as usage
    if duration_seconds < 10:
        return False, f"call_too_short:{duration_seconds:.2f}s"

    # All checks passed
    return True, ""


def _resolve_greeting(first_message: str, timezone_str: str, language: str) -> str:
    """Resolve ``{{greet}}`` placeholder in *first_message* to a time-based greeting.

    If the placeholder is absent the message is returned unchanged.  If the
    language or timezone are not supported the placeholder is silently removed.
    """
    if "{{greet}}" not in first_message:
        return first_message

    lang = language.lower()
    greetings = _TIMEZONE_GREETINGS.get(lang)
    if not greetings:
        logger.warning(
            f"[_resolve_greeting] Language {language} not supported for time-based greeting"
        )
        return first_message.replace("{{greet}}", "").strip()

    try:
        tz = pytz.timezone(timezone_str)
        current_hour = datetime.now(tz).hour
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"[_resolve_greeting] Invalid timezone: {timezone_str}")
        return first_message.replace("{{greet}}", "").strip()

    if current_hour < 12:
        greeting = greetings["morning"]
    elif current_hour < 18:
        greeting = greetings["afternoon"]
    else:
        greeting = greetings["evening"]

    return first_message.replace("{{greet}}", greeting + " ")


async def init_voice_call(
    request: VoiceInitRequest,
    session: AsyncSession,
) -> VoiceInitResponse:
    """Initialize a voice call for the LiveKit agent worker.

    Replicates the essential setup from ``handle_assistant_request`` in the Vapi
    integration (project lookup, user resolution, conversation creation,
    subscription check, voice config retrieval) but returns structured JSON
    instead of a Vapi assistant payload.
    """
    # TODO: Remove per-step debug logging after LiveKit voice init is stable in production
    caller_number = request.caller_number
    dialed_number = request.dialed_number
    call_id = request.call_id

    _log_extra = {
        "caller_number": caller_number,
        "dialed_number": dialed_number,
        "call_id": call_id,
    }

    logger.info("[init_voice_call] Started", extra=_log_extra)

    # --- Step 1: Build Message object for service layer ---
    message = Message(
        id=str(uuid.uuid4()),
        author_type=AuthorType.SYSTEM,
        sender_identifier=caller_number,
        recipient_identifier=dialed_number,
        channel=Channel.VOICE,
        broker=None,
        type=Type.TEXT,
        text=TextObject(body="[Call initiated]"),
        context="",
        extras=Extras(),
        metadata=Metadata(),
        timestamp=datetime.now(timezone.utc),
    )

    # --- Step 2: Resolve project by phone number ---
    project = await project_service.get_project_async(session, message)
    if not project:
        logger.error("[init_voice_call] Project not found", extra=_log_extra)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found for dialed number",
            headers={"Content-Type": "application/json"},
        )

    logger.info(
        "[init_voice_call] Step 2 done: project=%s", project.id, extra=_log_extra
    )

    # --- Step 3: Get or create user ---
    user, _ = await user_service.get_user_async(session, project, message)
    if not user:
        user = await user_service.create_user_async(session, project, message)
        await session.refresh(user, attribute_names=["id"])
        await session.refresh(project, attribute_names=["id"])

    await session.refresh(project, attribute_names=["id", "account"])

    logger.info("[init_voice_call] Step 3 done: user=%s", user.id, extra=_log_extra)

    # --- Step 4: Check subscription enforcement ---
    if await subscription_service.should_block_calls_async(session, project.account):
        logger.info(
            "LiveKit call blocked due to subscription enforcement",
            extra={
                "account_id": str(project.account.id),
                "call_id": call_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Voice calls are not available without an active subscription",
            headers={"Content-Type": "application/json"},
        )

    # --- Step 5: Create voice message / conversation ---
    message_repo = db.MessageRepositoryAsync(session)
    await message_repo.create_voice_message(
        user_id=user.id,
        project_id=project.id,
        message_body=message.to_dict(),
        call_id=call_id,
    )
    await session.refresh(user, attribute_names=["id"])
    await session.refresh(
        project,
        attribute_names=["id", "timezone", "transfer_phone_number", "transfer_message"],
    )

    logger.info("[init_voice_call] Step 5 done: conversation created", extra=_log_extra)

    logger.info("[init_voice_call] Step 5 done: conversation created", extra=_log_extra)

    # --- Step 6: Build caller_info ---
    # Capture project attributes into locals so later DB queries can't expire them.
    project_timezone = project.timezone
    project_transfer_phone = project.transfer_phone_number
    project_transfer_msg = project.transfer_message
    project_id = project.id

    caller_info = {
        "sender_identifier": caller_number,
        "recipient_identifier": dialed_number,
        "call_id": call_id,
        "timezone": project_timezone,
        "transfer_phone_number": project_transfer_phone,
        "transfer_message": project_transfer_msg,
    }

    # --- Step 7: Fetch voice configs ---
    voice_repo = VoiceConfigRepositoryAsync(session)
    voice_configs = await voice_repo.get_voice_configs_by_project(project_id)
    if not voice_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No voice configuration found for project {project_id}",
            headers={"Content-Type": "application/json"},
        )

    # Pick the first non-triage config (language assistant)
    non_triage = [vc for vc in voice_configs if vc.language.lower() != "triage"]
    if not non_triage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No language voice configuration found",
            headers={"Content-Type": "application/json"},
        )

    vc = non_triage[0]

    logger.info(
        "[init_voice_call] Step 7 done: voice_config language=%s",
        vc.language,
        extra=_log_extra,
    )

    # --- Step 8: Resolve greeting ---
    caller_timezone = project_timezone or "America/Los_Angeles"
    first_message = _resolve_greeting(
        vc.first_message or "Hi, how can I help you today?",
        caller_timezone.strip(),
        vc.language,
    )

    # --- Step 9: Map speech rate to float ---
    speech_rate = _SPEECH_RATE_TO_FLOAT.get(vc.speech_rate, 1.0)

    # --- Step 10: Determine STT config ---
    lang_lower = vc.language.lower()
    if vc.transcriber:
        stt_model = vc.transcriber.get("model", "nova-3")
        stt_language = vc.transcriber.get("language", "en-US")
    else:
        stt_cfg = _STT_CONFIGS.get(lang_lower, _STT_CONFIGS["english"])
        stt_model = stt_cfg["model"]
        stt_language = stt_cfg["language"]

    logger.info("[init_voice_call] Completed successfully", extra=_log_extra)

    return VoiceInitResponse(
        caller_info=caller_info,
        voice_id=vc.voice_id,
        voice_model=vc.voice_model or "sonic-3",
        speech_rate=speech_rate,
        first_message=first_message,
        language=vc.language,
        stt_model=stt_model,
        stt_language=stt_language,
        background_sound=vc.background_sound or None,
        replacements=vc.replacements or {},
    )


async def end_voice_call(
    request: VoiceEndCallRequest,
    session: AsyncSession,
) -> dict:
    """End a voice call from the LiveKit agent worker.

    Extracts call analytics, updates conversation, creates phone call record, and sends Stripe meter event.

    Args:
        request: VoiceEndCallRequest containing call details
        session: Database session

    Returns:
        dict: Status response with conversation_id if found
    """
    from db.repositories.conversation_repository import ConversationUpdate
    from db.repositories.phone_call_repository import PhoneCallRepositoryAsync
    from db.tables.conversations import ConversationStatus
    from services.subscription_service.stripe_usage_billing import send_meter_event

    call_id = request.call_id
    caller_number = request.caller_number
    dialed_number = request.dialed_number
    duration_seconds = request.duration_seconds
    close_reason = request.close_reason
    conversation_history = request.conversation

    _log_extra = {
        "call_id": call_id,
        "caller_number": caller_number,
        "dialed_number": dialed_number,
        "duration_seconds": duration_seconds,
        "close_reason": close_reason,
    }

    logger.info("[end_voice_call] Received end-call request", extra=_log_extra)

    # --- Step 1: Find conversation by call_id ---
    conversation_repo = db.ConversationRepositoryAsync(session)
    conversation = await conversation_repo.get_conversation_by_call_id(call_id)

    if not conversation:
        logger.error(
            "[end_voice_call] Conversation not found",
            extra={
                "call_info": {
                    "call_id": call_id,
                    "caller_number": caller_number,
                    "dialed_number": dialed_number,
                }
            },
        )
        return {
            "status": "error",
            "message": f"No conversation found for call_id: {call_id}",
        }

    conversation_id = conversation.id

    logger.info(
        f"[end_voice_call] Found conversation_id: {conversation_id}", extra=_log_extra
    )

    # Store conversation attributes before atomic close to avoid session detachment issues
    # After atomic_close_conversation() commits, the conversation object becomes detached
    project_id_for_billing = conversation.project_id
    user_id_for_event = conversation.user_id
    channel_for_event = conversation.channel.value if conversation.channel else "voice"
    is_test_for_event = conversation.is_test or False
    customer_converted_for_event = conversation.customer_converted

    # --- Step 2: Extract call analytics using LLM with retry ---
    analytics = None
    if conversation_history:
        try:
            analytics = await _call_analytics_with_retry(conversation_history)
            if analytics:
                logger.info(
                    f"[end_voice_call] Analytics extracted for conversation_id: {conversation_id}",
                    extra={
                        "conversation_id": str(conversation_id),
                        "analytics": {
                            "ended_reason": analytics["ended_reason"].value,
                            "call_purpose": [
                                p.value for p in analytics["call_purpose"]
                            ],
                            "user_satisfaction": analytics["user_satisfaction"].value,
                            "language": analytics["language"].value,
                        },
                    },
                )
        except Exception as e:
            logger.error(
                f"[end_voice_call] Failed to extract analytics after retries: {e}",
                extra={"conversation_id": str(conversation_id), "error": str(e)},
            )

    # Use default analytics if extraction failed
    if not analytics:
        logger.warning(
            f"[end_voice_call] Using default analytics for conversation_id: {conversation_id}"
        )
        analytics = _get_default_analytics()

    # --- Step 3: Atomically close conversation (single-writer gate) ---
    # This atomic operation ensures only one process can close the conversation
    # and prevents duplicate side-effects (phone call records, billing events)
    try:
        # Convert call_purpose list to comma-separated string for storage
        purpose_str = ",".join([p.value for p in analytics["call_purpose"]])

        # Check if customer converted (paid order exists) and update if not already set
        customer_converted_id = conversation.customer_converted
        if not customer_converted_id:
            # Query for any paid orders for this conversation
            from sqlalchemy import select

            from db.tables.orders import Order

            result = await session.execute(
                select(Order)
                .filter(
                    Order.conversation_id == conversation_id,
                    Order.status == "paid",
                )
                .order_by(Order.created_at.desc())
                .limit(1)
            )
            paid_order = result.scalar_one_or_none()

            if paid_order:
                customer_converted_id = paid_order.id
                logger.info(
                    f"[end_voice_call] Found paid order for conversation: {customer_converted_id}",
                    extra={"conversation_id": str(conversation_id)},
                )

        update_data = ConversationUpdate(
            status=ConversationStatus.CLOSED,
            purpose=purpose_str,
            language=analytics["language"].value,
            ended_reason=analytics["ended_reason"].value,
            customer_converted=customer_converted_id,
        )

        # Atomic close: returns True only if this process won the race to close
        successfully_closed = await conversation_repo.atomic_close_conversation(
            conversation_id, update_data
        )

        if not successfully_closed:
            # Another process already closed this conversation
            logger.warning(
                "[end_voice_call] Conversation already closed by another process - skipping side-effects",
                extra={
                    "call_info": {
                        "call_id": call_id,
                        "caller_number": caller_number,
                        "dialed_number": dialed_number,
                    },
                    "conversation_id": str(conversation_id),
                },
            )
            return {
                "status": "success",
                "conversation_id": str(conversation_id),
                "message": "Conversation already closed by another process",
            }

        logger.info(
            f"[end_voice_call] Conversation atomically closed: {conversation_id}",
            extra={"conversation_id": str(conversation_id)},
        )
    except Exception as e:
        logger.error(
            f"[end_voice_call] Failed to close conversation: {e}",
            extra={"conversation_id": str(conversation_id), "error": str(e)},
        )
        # Return error - do not proceed with side-effects if close failed
        return {
            "status": "error",
            "conversation_id": str(conversation_id),
            "message": f"Failed to close conversation: {str(e)}",
        }

    # Track failures for comprehensive error reporting
    phone_call_error: str | None = None
    billing_error: str | None = None

    # --- Step 4: Create phone call record ---
    try:
        phone_call_repo = PhoneCallRepositoryAsync(session)
        phone_call = await phone_call_repo.create_phone_call(
            call_id=call_id,
            conversation_id=conversation_id,
            duration=duration_seconds,
            ended_reason=analytics["ended_reason"],
            call_purpose=analytics["call_purpose"],
            user_satisfaction=analytics["user_satisfaction"],
            language=analytics["language"],
        )
        await session.commit()
        logger.info(
            f"[end_voice_call] Phone call record created: {phone_call.id}",
            extra={
                "conversation_id": str(conversation_id),
                "phone_call_id": str(phone_call.id),
            },
        )
    except Exception as e:
        await session.rollback()
        phone_call_error = str(e)
        logger.error(
            f"[end_voice_call] Failed to create phone call record: {e}",
            extra={"conversation_id": str(conversation_id), "error": str(e)},
        )

    # --- Step 5: Send Stripe meter event if call should be tracked ---
    # Apply billing skip rules: test numbers, duration < 10s, customer didn't speak
    should_track, skip_reason = _should_track_call_usage(
        caller_number=caller_number,
        duration_seconds=duration_seconds,
        conversation_history=conversation_history,
    )

    if should_track:
        try:
            # Get project and account info for Stripe billing
            # Use stored project_id to avoid refreshing detached conversation object
            project = await project_service.get_project_by_id_async(
                session, project_id_for_billing
            )

            if project and project.account and project.account.stripe_customer_id:
                event_name = f"calls_{project.id}"
                stripe_customer_id = project.account.stripe_customer_id

                # Send meter event (returns True/False, logging is handled internally)
                send_meter_event(
                    event_name=event_name,
                    stripe_customer_id=stripe_customer_id,
                    value=1,
                    timestamp=datetime.now(timezone.utc),
                )
                logger.info(
                    f"[end_voice_call] Stripe meter event sent for call_id: {call_id}",
                    extra={
                        "conversation_id": str(conversation_id),
                        "event_name": event_name,
                    },
                )
            else:
                logger.warning(
                    "[end_voice_call] Cannot send Stripe meter event - missing project or stripe_customer_id",
                    extra={"conversation_id": str(conversation_id)},
                )
        except Exception as e:
            billing_error = str(e)
            logger.error(
                f"[end_voice_call] Failed to send Stripe meter event: {e}",
                extra={"conversation_id": str(conversation_id), "error": str(e)},
            )
    else:
        # Log why billing was skipped
        logger.info(
            f"[end_voice_call] Skipping call usage tracking for call_id: {call_id}: {skip_reason}",
            extra={
                "call_id": call_id,
                "conversation_id": str(conversation_id),
                "skip_reason": skip_reason,
                "caller_last4": caller_number[-4:] if caller_number else "",
            },
        )

    # Return appropriate response based on operation results
    if phone_call_error or billing_error:
        errors = []
        if phone_call_error:
            errors.append(f"Phone call record: {phone_call_error}")
        if billing_error:
            errors.append(f"Billing: {billing_error}")

        return {
            "status": "partial_failure",
            "conversation_id": str(conversation_id),
            "message": f"Conversation closed but post-processing failed: {'; '.join(errors)}",
            "errors": {
                "phone_call_record": phone_call_error,
                "billing": billing_error,
            },
        }

    # Publish conversation evaluation event (fire-and-forget)
    # Pass primitive values — the background task creates its own DB session
    # Use stored values to avoid accessing detached conversation object
    _task = asyncio.create_task(
        _publish_livekit_evaluation_event(
            conversation_id=conversation_id,
            user_id=user_id_for_event,
            project_id=project_id_for_billing,
            call_id=call_id,
            duration_seconds=duration_seconds,
            close_reason=close_reason,
            conversation_history=conversation_history,
            analytics=analytics if conversation_history else None,
            channel=channel_for_event,
            is_test=is_test_for_event,
            customer_converted=customer_converted_for_event,
        )
    )

    return {
        "status": "success",
        "conversation_id": str(conversation_id),
    }


async def _call_analytics_with_retry(
    conversation_history: list[dict],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> dict | None:
    """Retry wrapper with exponential backoff for LLM analytics extraction.

    Args:
        conversation_history: List of message dicts with 'role' and 'content'
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff

    Returns:
        dict with normalized enum instances for all analytics fields, or None if all retries failed
    """
    import asyncio

    from services.analytics_service._utils import extract_call_analytics

    for attempt in range(max_retries):
        try:
            result = await extract_call_analytics(conversation_history)

            # Validate the response
            if _validate_analytics_response(result):
                # Normalize to ensure all fields are enum instances
                normalized_result = _normalize_analytics_to_enums(result)
                return normalized_result
            else:
                logger.warning(
                    f"[_call_analytics_with_retry] Invalid analytics response on attempt {attempt + 1}/{max_retries}"
                )

        except Exception as e:
            logger.warning(
                f"[_call_analytics_with_retry] Analytics extraction failed on attempt {attempt + 1}/{max_retries}: {e}"
            )

        # Wait before retry (exponential backoff)
        if attempt < max_retries - 1:
            delay = base_delay * (2**attempt)
            await asyncio.sleep(delay)

    logger.error(
        f"[_call_analytics_with_retry] All {max_retries} retry attempts failed"
    )
    return None


def _validate_analytics_response(result: dict) -> bool:
    """Validate LLM response has required fields and valid enum values.

    Args:
        result: Analytics dict from LLM extraction

    Returns:
        bool: True if valid, False otherwise
    """
    from db.tables.types import (
        CallEndedReason,
        CallLanguage,
        CallPurpose,
        UserSatisfaction,
    )

    try:
        # Check required keys exist
        required_keys = [
            "ended_reason",
            "call_purpose",
            "user_satisfaction",
            "language",
        ]
        if not all(key in result for key in required_keys):
            logger.warning(
                f"[_validate_analytics_response] Missing required keys. Got: {list(result.keys())}"
            )
            return False

        # Validate call_purpose is a list
        if not isinstance(result["call_purpose"], list):
            logger.warning(
                f"[_validate_analytics_response] call_purpose is not a list: {type(result['call_purpose'])}"
            )
            return False

        # Validate enum values by trying to construct them
        _ = CallEndedReason(result["ended_reason"])
        _ = [CallPurpose(p) for p in result["call_purpose"]]
        _ = UserSatisfaction(result["user_satisfaction"])
        _ = CallLanguage(result["language"])

        return True

    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"[_validate_analytics_response] Validation failed: {e}")
        return False


def _normalize_analytics_to_enums(result: dict) -> dict:
    """Normalize analytics dict to ensure all fields are Enum instances.

    Converts any string values to their corresponding enum instances to prevent
    errors when accessing .value attributes.

    Args:
        result: Analytics dict that may contain strings or enum instances

    Returns:
        dict: Normalized analytics with all enum instances
    """
    from db.tables.types import (
        CallEndedReason,
        CallLanguage,
        CallPurpose,
        UserSatisfaction,
    )

    return {
        "ended_reason": CallEndedReason(result["ended_reason"]),
        "call_purpose": [CallPurpose(p) for p in result["call_purpose"]],
        "user_satisfaction": UserSatisfaction(result["user_satisfaction"]),
        "language": CallLanguage(result["language"]),
    }


def _get_default_analytics() -> dict:
    """Return safe default analytics when LLM extraction fails.

    Returns:
        dict: Default analytics with enum values
    """
    from db.tables.types import (
        CallEndedReason,
        CallLanguage,
        CallPurpose,
        UserSatisfaction,
    )

    return {
        "ended_reason": CallEndedReason.other,
        "call_purpose": [CallPurpose.other],
        "user_satisfaction": UserSatisfaction.neutral,
        "language": CallLanguage.english,
    }


def _extract_transcript_text(msg: dict) -> str:
    """Safely extract text from a conversation history message."""
    content = msg.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return content[0].get("text", "")
    return str(content or "")


async def _publish_livekit_evaluation_event(
    conversation_id,
    user_id,
    project_id,
    call_id: str,
    duration_seconds: float,
    close_reason: str,
    conversation_history: list[dict],
    analytics: dict | None,
    channel: str,
    is_test: bool,
    customer_converted,
) -> None:
    """Publish ConversationEvaluationRequested for a LiveKit call. Fire-and-forget.

    Creates its own DB session to avoid using the request-scoped session
    which may close before this background task completes.
    """
    from db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            # Load project and account for identification fields
            project_repo = db.ProjectRepositoryAsync(session)
            project = await project_repo.get_project(project_id)
            if not project:
                logger.warning(
                    "[_publish_livekit_evaluation_event] Project not found",
                    extra={"conversation_id": str(conversation_id)},
                )
                return

            await session.refresh(project, attribute_names=["account"])
            account_name = (project.account.name or "") if project.account else ""

        # Build transcript from conversation history
        transcript = [
            {
                "speaker": "agent" if msg.get("role") == "assistant" else "user",
                "text": _extract_transcript_text(msg),
                "start_time": 0.0,  # LiveKit agent doesn't send per-turn timestamps yet
                "end_time": 0.0,
            }
            for msg in conversation_history
            if msg.get("role") in ("assistant", "user")
        ]

        event = ConversationEvaluationRequested(
            conversation_id=conversation_id,
            call_id=call_id,
            user_id=user_id,
            account_id=project.account_id,
            account_name=account_name,
            project_id=project.id,
            channel=channel,
            is_test=is_test,
            call_metadata={
                "duration_seconds": duration_seconds,
                "ended_reason": (
                    analytics["ended_reason"].value if analytics else close_reason
                ),
                "call_purpose": (
                    [p.value for p in analytics["call_purpose"]] if analytics else []
                ),
                "language": (analytics["language"].value if analytics else "english"),
                "user_satisfaction": (
                    analytics["user_satisfaction"].value if analytics else "neutral"
                ),
                "customer_converted": (
                    str(customer_converted) if customer_converted else None
                ),
                "room_name": None,
            },
            transcript=transcript,
            tool_calls=[],  # LiveKit tool call extraction not yet available here
            turn_latencies_ms=[],  # Not available from LiveKit agent HTTP report
        )

        published = await publish_event(event)
        if published:
            logger.info(
                "[_publish_livekit_evaluation_event] Published ConversationEvaluationRequested",
                extra={"call_id": call_id, "conversation_id": str(conversation_id)},
            )
        else:
            logger.warning(
                "[_publish_livekit_evaluation_event] publish_event returned False",
                extra={"call_id": call_id, "conversation_id": str(conversation_id)},
            )
    except Exception as e:
        logger.warning(
            f"[_publish_livekit_evaluation_event] Failed to publish event: {e}",
            extra={"conversation_id": str(conversation_id)},
        )
