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

    Logs call details and finds the conversation_id associated with the call_id.

    Args:
        request: VoiceEndCallRequest containing call details
        session: Database session

    Returns:
        dict: Status response with conversation_id if found
    """
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
        "conversation_messages": conversation_history,
    }

    logger.info("[end_voice_call] Received end-call request", extra=_log_extra)

    # Find conversation by call_id
    conversation_repo = db.ConversationRepositoryAsync(session)
    conversation = await conversation_repo.get_conversation_by_call_id(call_id)

    if not conversation:
        logger.warning(
            f"[end_voice_call] No conversation found for call_id: {call_id}",
            extra=_log_extra,
        )
        return {
            "status": "error",
            "message": f"No conversation found for call_id: {call_id}",
        }

    conversation_id = str(conversation.id)

    logger.info(
        f"[end_voice_call] Found conversation_id: {conversation_id}",
        extra={**_log_extra, "conversation_id": conversation_id},
    )

    # Extract call analytics using LLM
    analytics = None
    if conversation_history:
        try:
            from services.analytics_service._utils import extract_call_analytics

            analytics = await extract_call_analytics(conversation_history)
            logger.info(
                f"[end_voice_call] Analytics extracted for conversation_id: {conversation_id}",
                extra={
                    "conversation_id": conversation_id,
                    "analytics": {
                        "ended_reason": analytics["ended_reason"].value,
                        "call_purpose": [p.value for p in analytics["call_purpose"]],
                        "user_satisfaction": analytics["user_satisfaction"].value,
                        "language": analytics["language"].value,
                    },
                },
            )
        except Exception as e:
            analytics = None
            logger.error(
                f"[end_voice_call] Failed to extract analytics: {e}",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )

    # Publish conversation evaluation event (fire-and-forget)
    # Pass primitive values — the background task creates its own DB session
    _task = asyncio.create_task(
        _publish_livekit_evaluation_event(
            conversation_id=conversation.id,
            user_id=conversation.user_id,
            project_id=conversation.project_id,
            call_id=call_id,
            duration_seconds=duration_seconds,
            close_reason=close_reason,
            conversation_history=conversation_history,
            analytics=analytics if conversation_history else None,
            channel=conversation.channel.value if conversation.channel else "voice",
            is_test=conversation.is_test or False,
            customer_converted=conversation.customer_converted,
        )
    )

    return {
        "status": "success",
        "conversation_id": conversation_id,
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
