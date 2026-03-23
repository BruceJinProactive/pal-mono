"""Implementation for LiveKit voice call initialization endpoint."""

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone

import pytz
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

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
from events import (
    AudioRecordingReference,
    ConversationEvaluationRequested,
    publish_event,
)
from services import project_service, user_service
from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Track background tasks so they aren't garbage-collected before completion.
_background_tasks: set[asyncio.Task[object]] = set()

# S3 URI validation pattern
_S3_URI_PATTERN = re.compile(r"^s3://[a-z0-9][a-z0-9.-]*[a-z0-9]/.+$")


# Numeric speed mapping matching CARTESIA_SONIC3_SPEED_MAPPING from
# services/voice_service/providers/vapi/_implementation.py
_SPEECH_RATE_TO_FLOAT: dict[SpeechRate, float] = {
    SpeechRate.slowest: 0.6,
    SpeechRate.slower: 0.8,
    SpeechRate.normal: 1.0,
    SpeechRate.faster: 1.25,
    SpeechRate.fastest: 1.5,
}

# Mapping from raw LiveKit close_reason strings to CallEndedReason enum values.
# LiveKit sends hyphenated strings; the evaluator expects underscore enum values.
_LIVEKIT_CLOSE_REASON_MAP: dict[str, str] = {
    "customer-ended-call": "customer_ended",
    "assistant-forwarded-call": "assistant_forwarded",
    "twilio-reported-customer-misdialed": "misdialed",
    "silence-timed-out": "silence_timeout",
    "exceeded-max-duration": "max_duration_exceeded",
    "other": "other",
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
    1. Exclude test phone numbers (Palona internal) - only in production
    2. Exclude calls less than 10 seconds in duration
    3. Exclude calls where customer didn't speak

    Args:
        caller_number: Customer phone number
        duration_seconds: Call duration in seconds
        conversation_history: List of message dicts with 'role' and 'content'

    Returns:
        tuple: (should_track: bool, skip_reason: str)
    """
    # Rule 1: Check if test phone number (only in production)
    runtime_env = os.getenv("RUNTIME_ENV", "dev")
    if runtime_env == "prd" and _is_test_phone_number(caller_number):
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
    voice config retrieval) but returns structured JSON
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

    # --- Step 4: Create voice message / conversation ---
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

    logger.info("[init_voice_call] Step 4 done: conversation created", extra=_log_extra)

    # --- Step 5: Build caller_info ---
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

    # --- Step 6: Fetch voice configs ---
    voice_repo = VoiceConfigRepositoryAsync(session)
    voice_configs = await voice_repo.get_voice_configs_by_project(project_id)
    if not voice_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No voice configuration found for project {project_id}",
            headers={"Content-Type": "application/json"},
        )

    voice_configs = [
        voice_config
        for voice_config in voice_configs
        if voice_config.language != "triage"
    ]

    if not voice_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No language voice configuration found",
            headers={"Content-Type": "application/json"},
        )

    # Collect all languages from voice configs
    all_languages = []
    for voice_config in voice_configs:
        # Split combined languages like "english+spanish" into separate languages
        if "+" in voice_config.language:
            all_languages.extend(voice_config.language.split("+"))
        else:
            all_languages.append(voice_config.language)

    # Remove duplicates while preserving order
    languages = list(dict.fromkeys(all_languages))

    # Select voice config for other fields (prefer English, otherwise use first)
    if len(voice_configs) == 1:
        vc = voice_configs[0]
    else:
        english_configs = [
            vc for vc in voice_configs if "english" in vc.language.lower()
        ]
        vc = english_configs[0] if english_configs else voice_configs[0]

    logger.info(
        "[init_voice_call] Step 6 done: found %s voice_configs, languages=%s",
        len(voice_configs),
        languages,
        extra=_log_extra,
    )

    # --- Step 7: Resolve greeting ---
    caller_timezone = project_timezone or "America/Los_Angeles"
    first_message = _resolve_greeting(
        vc.first_message or "Hi, how can I help you today?",
        caller_timezone.strip(),
        vc.language,
    )

    # --- Step 8: Map speech rate to float ---
    speech_rate = _SPEECH_RATE_TO_FLOAT.get(vc.speech_rate, 1.0)

    logger.info("[init_voice_call] Completed successfully", extra=_log_extra)

    return VoiceInitResponse(
        caller_info=caller_info,
        voice_id=vc.voice_id,
        speech_rate=speech_rate,
        first_message=first_message,
        languages=languages,
        background_sound=vc.background_sound or None,
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
    from db.repositories.phone_call_repository import PhoneCallRepositoryAsync
    from db.tables.conversations import ConversationStatus
    from services.subscription_service.stripe_usage_billing import send_meter_event

    call_id = request.call_id
    caller_number = request.caller_number
    dialed_number = request.dialed_number
    duration_seconds = request.duration_seconds
    close_reason = request.close_reason
    conversation_history = request.conversation
    audio_recording_s3_uri = request.audio_recording_s3_uri

    _log_extra = {
        "call_id": call_id,
        "caller_number": caller_number,
        "dialed_number": dialed_number,
        "duration_seconds": duration_seconds,
        "close_reason": close_reason,
        "has_audio_recording": audio_recording_s3_uri is not None,
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

    # Override ended_reason if call was transferred to human
    # This takes precedence over LLM-extracted analytics
    ended_reason_override = None
    if conversation.transfer_purpose:
        from db.tables.types import CallEndedReason

        ended_reason_override = CallEndedReason.assistant_forwarded
        logger.info(
            f"[end_voice_call] Overriding ended_reason to assistant_forwarded due to transfer_purpose: {conversation.transfer_purpose}",
            extra={"conversation_id": str(conversation_id)},
        )
        analytics["ended_reason"] = ended_reason_override

    # --- Step 3: Close conversation and create phone call record in a single transaction ---
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

        # Update conversation attributes directly (no intermediate commit)
        conversation.status = ConversationStatus.CLOSED
        conversation.purpose = purpose_str
        conversation.language = analytics["language"].value
        # Use override if transfer occurred, otherwise use LLM analytics
        conversation.ended_reason = (
            ended_reason_override.value
            if ended_reason_override
            else analytics["ended_reason"].value
        )
        conversation.customer_converted = customer_converted_id
        conversation.call_id = call_id

        # --- Step 4: update phone call record ---
        phone_call_repo = PhoneCallRepositoryAsync(session)
        phone_call = await phone_call_repo.update_phone_call(
            call_id=call_id,
            duration=duration_seconds,
            ended_reason=analytics["ended_reason"],
            call_purpose=analytics["call_purpose"],
            user_satisfaction=analytics["user_satisfaction"],
            language=analytics["language"],
        )

        # Store phone_call_id before commit to avoid accessing expired object attributes
        phone_call_id = None
        if not phone_call:
            logger.warning(
                f"[end_voice_call] Phone call record not found for call_id: {call_id}",
                extra={"conversation_id": str(conversation_id)},
            )
        else:
            phone_call_id = phone_call.id

        # Commit both updates together atomically
        await session.commit()

        logger.info(
            f"[end_voice_call] Conversation closed and phone call record updated for call {call_id}",
            extra={
                "conversation_id": str(conversation_id),
                "phone_call_id": str(phone_call_id) if phone_call_id else None,
            },
        )
    except Exception as e:
        await session.rollback()
        logger.error(
            f"[end_voice_call] Failed to close conversation or update phone call record: {e}",
            extra={"conversation_id": str(conversation_id), "error": str(e)},
        )
        # Return error - transaction failed
        return {
            "status": "error",
            "conversation_id": str(conversation_id),
            "message": f"Failed to close conversation: {str(e)}",
        }

    # Track failures for comprehensive error reporting
    billing_error: str | None = None

    # --- Step 5: Send Stripe meter event if call should be tracked ---
    # Apply billing skip rules: test numbers, duration < 10s, customer didn't speak
    should_track, skip_reason = _should_track_call_usage(
        caller_number=caller_number,
        duration_seconds=duration_seconds,
        conversation_history=conversation_history,
    )

    if should_track:
        try:
            # Load project and account relationship after commit to access stripe_customer_id
            # This follows the same pattern as Vapi integration (see vapi/_implementation.py:1296)
            logger.debug(
                f"[end_voice_call] Loading project for billing: project_id={project_id_for_billing}",
                extra={
                    "conversation_id": str(conversation_id),
                    "project_id": str(project_id_for_billing),
                },
            )

            project_for_billing = await project_service.get_project_by_id_async(
                session, project_id_for_billing
            )

            if not project_for_billing:
                logger.warning(
                    "[end_voice_call] Project not found for billing",
                    extra={
                        "conversation_id": str(conversation_id),
                        "project_id": str(project_id_for_billing),
                    },
                )
            else:
                logger.debug(
                    "[end_voice_call] Project loaded, refreshing account relationship",
                    extra={
                        "conversation_id": str(conversation_id),
                        "project_id": str(project_id_for_billing),
                    },
                )

                try:
                    await session.refresh(
                        project_for_billing, attribute_names=["account"]
                    )
                    logger.debug(
                        "[end_voice_call] Account relationship refreshed successfully",
                        extra={"conversation_id": str(conversation_id)},
                    )
                except Exception as refresh_error:
                    logger.error(
                        f"[end_voice_call] Failed to refresh account relationship: {refresh_error}",
                        extra={
                            "conversation_id": str(conversation_id),
                            "project_id": str(project_id_for_billing),
                            "error": str(refresh_error),
                        },
                    )
                    raise

                if not project_for_billing.account:
                    logger.warning(
                        "[end_voice_call] Project has no associated account",
                        extra={
                            "conversation_id": str(conversation_id),
                            "project_id": str(project_id_for_billing),
                        },
                    )
                elif not project_for_billing.account.stripe_customer_id:
                    logger.warning(
                        "[end_voice_call] Account has no stripe_customer_id",
                        extra={
                            "conversation_id": str(conversation_id),
                            "project_id": str(project_id_for_billing),
                            "account_id": str(project_for_billing.account.id),
                        },
                    )
                else:
                    # All validations passed, send meter event
                    event_name = f"calls_{project_id_for_billing}"
                    stripe_customer_id = project_for_billing.account.stripe_customer_id

                    logger.debug(
                        "[end_voice_call] Sending Stripe meter event",
                        extra={
                            "conversation_id": str(conversation_id),
                            "event_name": event_name,
                            "stripe_customer_id": stripe_customer_id,
                        },
                    )

                    # Send meter event (returns True/False, logging is handled internally)
                    # Run in thread pool to avoid SQLAlchemy async/sync context mixing
                    await asyncio.to_thread(
                        send_meter_event,
                        event_name=event_name,
                        stripe_customer_id=stripe_customer_id,
                        value=1,
                        timestamp=datetime.now(timezone.utc),
                    )

                    logger.info(
                        f"[end_voice_call] Stripe meter event sent successfully for call_id: {call_id}",
                        extra={
                            "conversation_id": str(conversation_id),
                            "event_name": event_name,
                        },
                    )
        except Exception as e:
            billing_error = str(e)
            logger.error(
                f"[end_voice_call] Failed to send Stripe meter event: {e}",
                extra={
                    "conversation_id": str(conversation_id),
                    "project_id": str(project_id_for_billing),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
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
    if billing_error:
        return {
            "status": "partial_failure",
            "conversation_id": str(conversation_id),
            "message": f"Conversation closed but billing failed: {billing_error}",
            "errors": {
                "billing": billing_error,
            },
        }

    # Build audio recording reference if URI provided
    audio_recording = _build_audio_recording_reference(
        audio_recording_s3_uri, duration_seconds
    )
    if audio_recording:
        logger.info(
            "[end_voice_call] Audio recording available",
            extra={
                "conversation_id": str(conversation_id),
                "audio_recording_uri_present": True,
            },
        )
    else:
        if audio_recording_s3_uri:
            logger.warning(
                "[end_voice_call] Audio recording URI provided but invalid",
                extra={"conversation_id": str(conversation_id)},
            )
        else:
            logger.debug(
                "[end_voice_call] No audio recording URI provided",
                extra={"conversation_id": str(conversation_id)},
            )

    # Publish conversation evaluation event (fire-and-forget)
    # Pass primitive values — the background task creates its own DB session
    # Use stored values to avoid accessing detached conversation object
    task = asyncio.create_task(
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
            audio_recording=audio_recording,
        )
    )
    _background_tasks.add(task)

    def _on_done(t: asyncio.Task[object]) -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error(
                "[Voice] Background evaluation task failed for conversation %s: %s",
                conversation_id,
                t.exception(),
                exc_info=t.exception(),
            )

    task.add_done_callback(_on_done)

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


def _build_audio_recording_reference(
    audio_recording_s3_uri: str | None,
    duration_seconds: float,
) -> AudioRecordingReference | None:
    """Build AudioRecordingReference from S3 URI, with validation.

    Args:
        audio_recording_s3_uri: S3 URI (e.g., "s3://bucket/key.wav")
        duration_seconds: Call duration in seconds

    Returns:
        AudioRecordingReference if URI is valid, None otherwise
    """
    if not audio_recording_s3_uri:
        return None

    # Validate S3 URI format
    if not _S3_URI_PATTERN.match(audio_recording_s3_uri):
        logger.warning("[_build_audio_recording_reference] Invalid S3 URI format")
        return None

    return AudioRecordingReference(
        s3_uri=audio_recording_s3_uri,
        duration_seconds=duration_seconds,
    )


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
    audio_recording: AudioRecordingReference | None,
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
                    analytics["ended_reason"].value
                    if analytics
                    else _LIVEKIT_CLOSE_REASON_MAP.get(close_reason, "other")
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
            audio_recording=audio_recording,
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


async def upload_recording(
    file: UploadFile, call_id: str, room_name: str
) -> dict[str, str]:
    """Upload an audio recording from the LiveKit agent worker to S3.

    Args:
        file: Audio file upload (OGG, WAV, or MP3)
        call_id: Unique call identifier
        room_name: LiveKit room name

    Returns:
        dict with audio_recording_s3_uri key containing the S3 URI

    Raises:
        HTTPException: If validation fails or S3 upload errors occur
    """
    # Get S3 configuration
    bucket_name = os.getenv("AUDIO_RECORDINGS_S3_BUCKET")
    if not bucket_name:
        logger.error("[upload_recording] AUDIO_RECORDINGS_S3_BUCKET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio recordings bucket not configured",
            headers={"Content-Type": "application/json"},
        )

    region = os.getenv("AWS_REGION", "us-east-1")

    _log_extra = {
        "call_id": call_id,
        "room_name": room_name,
        "upload_filename": file.filename,
    }

    # Validate filename is provided
    if not file.filename:
        logger.error("[upload_recording] No filename provided", extra=_log_extra)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
            headers={"Content-Type": "application/json"},
        )

    # Validate file extension
    filename = os.path.basename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    allowed_extensions = {".ogg", ".wav", ".mp3"}

    if ext not in allowed_extensions:
        logger.error(
            "[upload_recording] Unsupported file extension",
            extra={**_log_extra, "extension": ext},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension: {ext}. Allowed: .ogg, .wav, .mp3",
            headers={"Content-Type": "application/json"},
        )

    # Read file content
    try:
        file_content = await file.read()
    except Exception as e:
        logger.error(
            f"[upload_recording] Failed to read file content: {e}", extra=_log_extra
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read file content",
            headers={"Content-Type": "application/json"},
        ) from e

    # Validate file is not empty
    if not file_content:
        logger.error("[upload_recording] Empty file received", extra=_log_extra)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
            headers={"Content-Type": "application/json"},
        )

    # Validate file size (max 10MB)
    max_size_bytes = 10 * 1024 * 1024
    file_size = len(file_content)
    if file_size > max_size_bytes:
        logger.error(
            "[upload_recording] File too large",
            extra={**_log_extra, "size_bytes": file_size, "max_bytes": max_size_bytes},
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size {file_size} bytes exceeds maximum of {max_size_bytes} bytes",
            headers={"Content-Type": "application/json"},
        )

    # Sanitize room_name and call_id for safe S3 key construction
    # Allow only alphanumeric, hyphens, and underscores
    safe_room = re.sub(r"[^a-zA-Z0-9_-]", "_", room_name)
    safe_call_id = re.sub(r"[^a-zA-Z0-9_-]", "_", call_id)

    # Build S3 key: recordings/{room_name}/{call_id}.ogg (use original extension)
    s3_key = f"recordings/{safe_room}/{safe_call_id}{ext}"
    s3_uri = f"s3://{bucket_name}/{s3_key}"

    # Upload to S3
    try:
        from services.asset_service._utils import init_s3

        s3_client = init_s3(region)

        # Map extensions to MIME types for fallback
        ext_to_mime = {
            ".ogg": "audio/ogg",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
        }

        # Use put_object since files are small (<10MB)
        await run_in_threadpool(
            s3_client.put_object,
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_content,
            ContentType=file.content_type or ext_to_mime.get(ext, "audio/ogg"),
        )

        logger.info(
            "[upload_recording] Successfully uploaded audio recording",
            extra={
                **_log_extra,
                "s3_uri": s3_uri,
                "size_bytes": file_size,
            },
        )

        return {"audio_recording_s3_uri": s3_uri}

    except Exception as e:
        logger.error(
            f"[upload_recording] S3 upload failed: {e!s}",
            extra={**_log_extra, "s3_key": s3_key, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload to S3: {e!s}",
            headers={"Content-Type": "application/json"},
        ) from e
