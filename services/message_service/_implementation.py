import asyncio
import datetime
import random
import uuid
from collections.abc import Callable
from typing import Any, AsyncIterator

from agno.run.response import RunResponse
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta
from pal_agents import Agent as PalAgent
from pal_agents import Input as PalInput
from pal_agents.input import RuntimeContext
from pal_agents.spec import Spec
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import Agent
from agent.input_output import Output
from agent.storage._implementation import query_history_messages
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Extras,
    Message,
    Metadata,
    TextObject,
)
from db.pal_repository.catering_request import (
    CateringRequestRepository as CateringRequestRepositoryNew,
)
from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.session import AsyncSessionLocal
from db.tables.catering_requests import FulfillmentType
from db.tables.types import Channel
from services import (
    agent_service,
    catering_service,
    project_service,
    reservation_service,
    toast_checkout_service,
    transaction_service,
    user_service,
)
from utils.cache.tool_result_cache import append_tool_result, get_tool_results
from utils.eval_safety import apply_eval_safety
from utils.log import logger
from utils.otel import record_duration, trace_async_block
from utils.request_context import RequestContext

from . import _utils
from ._store_status import compute_store_status
from ._tracing import langfuse_message_span
from ._utils import EMAIL_BODY_EXTRACTION_TIMEOUT_SECONDS, _extract_email_body_from_s3

_background_tasks: set[asyncio.Task[None]] = set()


def _schedule_tool_result_cache_writes(
    conversation_id: uuid.UUID,
    events: list[dict[str, Any]],
) -> None:
    for event in events:
        if event.get("type") != "tool_call":
            continue

        payload = event.get("payload")
        if not isinstance(payload, dict):
            logger.info(
                "[tool_result_cache] Skipping tool_call event without dict payload",
                extra={"conversation_id": str(conversation_id)},
            )
            continue

        try:
            task = asyncio.create_task(
                append_tool_result(str(conversation_id), dict(payload))
            )
        except Exception:
            logger.warning(
                "Failed to schedule tool result cache write",
                extra={"conversation_id": str(conversation_id)},
                exc_info=True,
            )
            continue

        _background_tasks.add(task)
        task.add_done_callback(_handle_tool_result_cache_write_done)


def _handle_tool_result_cache_write_done(task: asyncio.Task[None]) -> None:
    _background_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        logger.debug("Tool result cache write task was cancelled")
    except Exception:
        logger.warning("Tool result cache write task failed", exc_info=True)


async def _hydrate_previous_tool_results(
    runtime_context: RuntimeContext,
    conversation_id: uuid.UUID,
) -> None:
    try:
        previous_tool_results = await get_tool_results(str(conversation_id))
    except Exception:
        logger.warning(
            "Failed to read previous tool results from cache",
            extra={"conversation_id": str(conversation_id)},
            exc_info=True,
        )
        return

    result_count = len(previous_tool_results)
    logger.info(
        "[tool_result_cache] Previous tool result cache %s before pal-agents run",
        "hit" if result_count else "miss",
        extra={
            "conversation_id": str(conversation_id),
            "result_count": result_count,
            "fallback": "process_local" if result_count == 0 else None,
        },
    )

    if result_count == 0:
        return

    try:
        setattr(runtime_context, "previous_tool_results", previous_tool_results)
    except Exception:
        logger.warning(
            "Failed to attach previous tool results to RuntimeContext",
            extra={
                "conversation_id": str(conversation_id),
                "result_count": result_count,
            },
            exc_info=True,
        )


def _serialize_prior_catering_request(request: CateringRequestData) -> dict[str, Any]:
    return {
        "id": str(request.id),
        "event_date": request.event_date.isoformat() if request.event_date else None,
        "event_time": request.event_time.isoformat() if request.event_time else None,
        "event_address": request.event_address,
        "event_detail": request.event_detail,
        "event_fulfillment": request.event_fulfillment,
        "party_size": request.party_size,
        "contact_name": request.contact_name,
        "contact_phone_number": request.contact_phone_number,
        "contact_email": request.contact_email,
        "status": request.status,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "all_items": request.all_items,
    }


async def _attach_prior_catering_requests_to_spec(
    session: AsyncSession,
    spec: Spec,
    project_id: uuid.UUID,
    customer_phone: str | None,
) -> None:
    if not getattr(spec, "catering_enabled", False) or not customer_phone:
        return

    prior_requests = await CateringRequestRepositoryNew(
        session
    ).list_by_project_id_and_phone(project_id, customer_phone)
    if prior_requests:
        setattr(
            spec,
            "prior_catering_requests",
            [_serialize_prior_catering_request(request) for request in prior_requests],
        )


def _parse_catering_overwrite_time(
    raw_value: str | None,
) -> tuple[datetime.date | None, datetime.time | None]:
    if not raw_value:
        return None, None
    value = raw_value.strip()
    for separator in ("T", " "):
        if separator in value:
            date_part, time_part = value.split(separator, 1)
            try:
                return (
                    datetime.date.fromisoformat(date_part),
                    datetime.time.fromisoformat(time_part[:5]),
                )
            except ValueError:
                return None, None
    try:
        return datetime.date.fromisoformat(value), None
    except ValueError:
        return None, None


def _select_catering_request_for_overwrite(
    requests: list[CateringRequestData],
    overwrite_time: str | None,
) -> CateringRequestData | None:
    if not requests:
        return None

    raw_overwrite_time = overwrite_time.strip() if overwrite_time else None
    if not raw_overwrite_time:
        return requests[0]

    target_date, target_time = _parse_catering_overwrite_time(raw_overwrite_time)
    if target_date is None:
        return requests[0]

    for request in requests:
        if request.event_date != target_date:
            continue
        if target_time is None or request.event_time == target_time:
            return request

    dated_requests = [request for request in requests if request.event_date is not None]
    if not dated_requests:
        return requests[0]

    if target_time is not None:
        target_datetime = datetime.datetime.combine(target_date, target_time)
        return min(
            dated_requests,
            key=lambda request: _catering_event_datetime_distance(
                request,
                target_datetime,
            ),
        )

    return min(
        dated_requests,
        key=lambda request: _catering_event_date_distance(request, target_date),
    )


def _catering_event_datetime_distance(
    request: CateringRequestData,
    target_datetime: datetime.datetime,
) -> float:
    if request.event_date is None:
        return float("inf")
    request_datetime = datetime.datetime.combine(
        request.event_date,
        request.event_time or datetime.time.min,
    )
    return abs((request_datetime - target_datetime).total_seconds())


def _catering_event_date_distance(
    request: CateringRequestData,
    target_date: datetime.date,
) -> int:
    if request.event_date is None:
        return 999999
    return abs((request.event_date - target_date).days)


def _parse_agent_catering_event_date(raw_value: str | None) -> datetime.date | None:
    if not raw_value:
        return None
    try:
        return datetime.date.fromisoformat(raw_value)
    except ValueError:
        logger.warning(
            "[catering] Ignoring invalid catering event_date from agent.",
            extra={"event_date": raw_value},
        )
        return None


async def _persist_catering_details_from_agent(
    session: AsyncSession,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    cd: Any,
) -> None:
    raw_event_fulfillment = getattr(cd, "event_fulfillment", None)
    raw_event_time = getattr(cd, "event_time", None)
    contact_phone_number = getattr(cd, "contact_phone_number", None)
    event_fulfillment = (
        FulfillmentType(raw_event_fulfillment) if raw_event_fulfillment else None
    )
    event_time = datetime.time.fromisoformat(raw_event_time) if raw_event_time else None
    event_date = _parse_agent_catering_event_date(getattr(cd, "event_date", None))
    contact_email = getattr(cd, "contact_email", None)
    all_items = getattr(cd, "all_items", None)
    should_overwrite = bool(getattr(cd, "overwrite", False))

    if should_overwrite:
        candidates = await CateringRequestRepositoryNew(
            session
        ).list_by_project_id_and_phone(project_id, contact_phone_number)
        existing_request = _select_catering_request_for_overwrite(
            candidates,
            getattr(cd, "overwrite_time", None),
        )
        if existing_request is not None:
            update_kwargs: dict[str, Any] = {
                "session": session,
                "catering_request_id": existing_request.id,
                "contact_name": cd.contact_name,
                "event_time": event_time,
                "event_address": cd.event_address,
                "event_detail": cd.event_detail,
                "event_fulfillment": event_fulfillment,
                "party_size": cd.party_size,
            }
            if event_date is not None:
                update_kwargs["event_date"] = event_date
            if contact_phone_number:
                update_kwargs["contact_phone_number"] = contact_phone_number
            if contact_email:
                update_kwargs["contact_email"] = contact_email
            if all_items is not None:
                update_kwargs["all_items"] = all_items
            await catering_service.update_catering_request(**update_kwargs)
            return

    await catering_service.create_catering_request_async(
        session=session,
        project_id=project_id,
        event_date=event_date,
        contact_name=cd.contact_name,
        contact_phone_number=contact_phone_number,
        contact_email=contact_email,
        event_time=event_time,
        event_address=cd.event_address,
        event_detail=cd.event_detail,
        all_items=all_items,
        event_fulfillment=event_fulfillment,
        party_size=cd.party_size,
        idempotency_key=str(conversation_id),
    )


async def _fingerprint_conversation(
    agent_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel: Channel,
) -> None:
    """Compute and store agent fingerprints for a conversation.

    Fire-and-forget background task. Owns its own session.
    Skips if conversation already has a fingerprint.
    """
    try:
        from services.agent_service._raw_config import RawConfig
        from services.eval_service._snapshot import upsert_agent_config_snapshot

        async with AsyncSessionLocal() as session:
            conversation_repo = db.ConversationRepositoryAsync(session)
            conversation = await conversation_repo.get_conversation_by_id(
                conversation_id
            )
            if conversation.agent_fingerprint:
                return

            agent_repo = db.AgentRepositoryAsync(session)
            db_agent = await agent_repo.get_agent(agent_id=agent_id)
            if not db_agent or not db_agent.account:
                return

            project_repo = db.ProjectRepositoryAsync(session)
            db_project = await project_repo.get_project(project_id)
            if not db_project:
                return

            raw_config = RawConfig(
                agent=db_agent,
                project=db_project,
                account=db_agent.account,
                user_id=user_id,
                conversation_id=conversation_id,
                channel=channel,
            )
            (
                config,
                agent_fp,
                prompt_fp,
                config_dict,
            ) = await raw_config.build_with_fingerprint(session)

            conversation.agent_fingerprint = agent_fp
            conversation.prompt_fingerprint = prompt_fp
            await session.commit()

            prompt_text = (config.persona.description if config else "") or ""
            await upsert_agent_config_snapshot(
                fingerprint=agent_fp,
                agent_id=agent_id,
                project_id=project_id,
                config_dict=config_dict,
                prompt_hash=prompt_fp,
                prompt_text=prompt_text,
            )
    except Exception:
        logger.exception("Failed to fingerprint conversation %s", conversation_id)


async def _process_toast_checkout_request_background(
    *,
    checkout_request: object,
    conversation_id: uuid.UUID,
    sender_identifier: str,
    recipient_identifier: str,
    broker: Broker | None,
) -> None:
    """Process Toast checkout request in a fire-and-forget task with its own DB session."""
    try:
        async with AsyncSessionLocal() as session:
            await toast_checkout_service.process_checkout_request_async(
                session=session,
                checkout_request=checkout_request,
                conversation_id=conversation_id,
                sender_identifier=sender_identifier,
                recipient_identifier=recipient_identifier,
                broker=broker,
            )
    except Exception:
        logger.warning(
            "[ToastCheckout] Background checkout processing failed",
            extra={"conversation_id": str(conversation_id)},
            exc_info=True,
        )


def _schedule_toast_checkout_request(
    *,
    checkout_request: object,
    conversation_id: uuid.UUID,
    sender_identifier: str,
    recipient_identifier: str,
    broker: Broker | None,
) -> None:
    try:
        task = asyncio.create_task(
            _process_toast_checkout_request_background(
                checkout_request=checkout_request,
                conversation_id=conversation_id,
                sender_identifier=sender_identifier,
                recipient_identifier=recipient_identifier,
                broker=broker,
            )
        )
    except Exception:
        logger.warning(
            "[ToastCheckout] Failed to schedule checkout processing",
            extra={"conversation_id": str(conversation_id)},
            exc_info=True,
        )
        return

    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _is_toast_checkout_request(checkout_request: object) -> bool:
    if isinstance(checkout_request, dict):
        request_type = checkout_request.get("type")
        provider = checkout_request.get("provider")
    else:
        request_type = getattr(checkout_request, "type", None)
        provider = getattr(checkout_request, "provider", None)

    return request_type == "payment_checkout" and provider == "toast"


def get_filler_message(message: Message) -> Message:
    # Collection of filler phrases for voice responses
    FILLER_PHRASES = [
        "Working on it.",
        "Bear with me.",
        "One brief moment.",
        "Brief moment.",
        "Working on your request.",
        "Just a short wait.",
    ]
    # Randomly select a filler phrase
    filler_content = random.choice(FILLER_PHRASES)
    filler_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier=message.recipient_identifier,
        recipient_identifier=message.sender_identifier,
        channel=message.channel,
        broker=message.broker,
        text=TextObject(body=filler_content),
        metadata=message.metadata,
    )

    return filler_message


async def _apply_test_safety_if_needed(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    spec: Spec,
) -> None:
    """Auto-apply :func:`utils.eval_safety.apply_eval_safety` for test convos.

    Runs once per spec construction, immediately after
    :func:`agent_service.construct_agent_spec`. When the conversation is
    flagged ``is_test=True`` (set by ``metadata.testing=True`` on the
    first message), side-effecting providers are hardened in place:

    * ``spec.toast.submit_orders=False``
    * ``spec.adora.force_payment_link=True``

    This closes the long-standing gap where eval drivers that hit
    ``get_chat_response_stream`` via HTTP had no way to install a
    ``spec_modifier``. By gating on the persisted ``Conversation.is_test``
    rather than an in-memory flag, the safety applies uniformly to every
    caller path (InProcessDriver, HttpVoiceDriver, LiveKit real-voice
    evals, direct HTTP) without each needing to plumb its own modifier.

    Errors (e.g. conversation row not found) are logged and swallowed —
    a fetch failure must not turn into a safety bypass, so we err on the
    side of continuing with whatever the spec already is.
    """
    try:
        conversation = await db.ConversationRepositoryAsync(
            session
        ).get_conversation_by_id(conversation_id=conversation_id)
        is_test = bool(conversation and conversation.is_test)
    except ValueError:
        # get_conversation_by_id raises when the row is missing; nothing
        # to harden against.
        return
    except Exception:
        logger.exception(
            "Failed to look up conversation for eval-safety check "
            "(conversation_id=%s); skipping auto-apply",
            conversation_id,
        )
        return

    if is_test:
        apply_eval_safety(spec)
        logger.debug(
            "Applied eval safety to Spec for test conversation %s",
            conversation_id,
        )


async def _dispatch_agent_async(
    *,
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    use_pal_agents: bool,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    project_account_id: uuid.UUID,
    project_raw_config: dict,
    project_timezone: str | None,
    project_business_hours: dict | None = None,
    project_store_hours: str | None = None,
    account_name: str,
    conversation_id: uuid.UUID,
    context_modifier: Callable[[RuntimeContext], None] | None = None,
    spec_modifier: Callable[[Spec], None] | None = None,
) -> tuple[Output, list[dict]]:
    """Dispatch to pal-agents or legacy agent and return (Output, events)."""
    collected_events: list[dict] = []

    if use_pal_agents:
        spec = await agent_service.construct_agent_spec(
            session=session,
            agent_id=agent_id,
            user_id=user_id,
            project_id=project_id,
            conversation_id=conversation_id,
            channel=message.channel,
            sender_identifier=message.sender_identifier,
            raw_config=project_raw_config,
        )

        # Auto-harden Spec whenever the Conversation is flagged as test.
        # Runs BEFORE the caller-provided ``spec_modifier`` so deliberate
        # overrides (e.g. integration tests that want submit_orders=True
        # against a mocked HTTP client) still win.
        await _apply_test_safety_if_needed(session, conversation_id, spec)

        customer_phone = None
        if message.channel and message.channel.value.lower() in [
            "sms",
            "voice",
            "whatsapp",
        ]:
            customer_phone = message.sender_identifier

        await _attach_prior_catering_requests_to_spec(
            session, spec, project_id, customer_phone
        )

        if spec_modifier:
            spec_modifier(spec)

        pal_agent = PalAgent(spec=spec)

        store_status = compute_store_status(
            project_business_hours, project_store_hours, project_timezone
        )

        runtime_context = RuntimeContext(
            user_id=str(user_id),
            session_id=str(conversation_id),
            customer_phone=customer_phone,
            project_id=str(project_id),
            account_id=str(project_account_id),
            account_name=account_name,
            agent_id=str(agent_id),
            timezone=project_timezone or "America/Los_Angeles",
            channel=message.channel.value,
            store_status=store_status,
        )

        await _hydrate_previous_tool_results(runtime_context, conversation_id)

        if context_modifier:
            context_modifier(runtime_context)

        # Fetch conversation history
        history_messages = await query_history_messages(
            conversation_id,
            limit=100,
        )

        current_message = message.text.body if message.text else ""
        message_id = message.channel_info.get("messageId")
        logger.debug(f"processing input message: {message_id}, {message.channel}")

        # Handle email body extraction from S3
        if message.channel == Channel.EMAIL and message.channel_info.get("messageId"):
            message_id = message.channel_info["messageId"]
            logger.info(f"Extracting email body for message ID: {message_id}")
            try:
                current_message = await asyncio.wait_for(
                    _extract_email_body_from_s3(
                        message_id,
                        fallback_body=current_message,
                    ),
                    timeout=EMAIL_BODY_EXTRACTION_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out extracting email body from S3 for "
                    f"message_id {message_id}"
                )

        history_text = ""
        if history_messages:
            if (
                history_messages[-1].content == current_message
                and history_messages[-1].role == "user"
            ):
                prior_messages = history_messages[:-1]
            else:
                logger.warning(
                    "[pal-agents] Last history message does not match current input. "
                    f"Expected: {current_message[:50]}..., "
                    f"Got: {(history_messages[-1].content or '')[:50]}..."
                )
                prior_messages = history_messages

            if prior_messages:
                history_text = "\n".join(
                    [
                        f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content}"
                        for msg in prior_messages
                        if msg.content
                    ]
                )

        # Build content with history
        if history_text:
            full_content = (
                f"<conversation_history>\n{history_text}\n</conversation_history>\n\n"
                f"User: {current_message}"
            )
        else:
            full_content = f"User: {current_message}"

        pal_input = PalInput(
            content=full_content,
            runtime_context=runtime_context,
        )

        pal_output = await pal_agent.run(pal_input)

        # Log order_details if present and persist to DB
        if hasattr(pal_output, "order_details") and pal_output.order_details:
            order_details = pal_output.order_details
            logger.info(
                "[order_details]Order successfully placed",
                extra={
                    "event_type": "order_placed",
                    "conversation_id": str(conversation_id),
                    "agent_id": str(agent_id),
                    "account_name": account_name,
                    "vendor": order_details.vendor,
                    "order_id": order_details.order_id,
                    "store_id": order_details.store_id,
                    "user_phone_number": order_details.user_phone_number,
                    "tracking_link": order_details.tracking_link,
                    "status": order_details.status,
                    "fulfillment_strategy": order_details.fulfillment_strategy,
                    "subtotal": float(order_details.subtotal),
                    "tax": float(order_details.tax),
                    "service_charge": float(order_details.service_charge),
                    "delivery_charge": float(order_details.delivery_charge),
                    "discount": float(order_details.discount),
                    "total": float(order_details.total),
                    "item_count": len(order_details.order_items),
                    "order_time": order_details.order_time,
                },
            )

            await transaction_service.create_order_from_agent_async(
                session=session,
                order_details=order_details,
                conversation_id=conversation_id,
            )

        # Persist reservation_details if present
        if (
            hasattr(pal_output, "reservation_details")
            and pal_output.reservation_details
        ):
            rd = pal_output.reservation_details
            logger.info(
                "[reservation_details]Reservation/waitlist placed",
                extra={
                    "event_type": "reservation_placed",
                    "conversation_id": str(conversation_id),
                    "agent_id": str(agent_id),
                    "account_name": account_name,
                    "vendor": rd.vendor,
                    "entry_type": rd.entry_type,
                    "reservation_id": rd.reservation_id,
                    "store_id": rd.store_id,
                    "status": rd.status,
                    "party_size": rd.party_size,
                },
            )
            await reservation_service.save_reservation_from_agent_async(
                session=session,
                reservation_details=rd,
                conversation_id=conversation_id,
            )

        # Persist catering_details if present
        # (guarded by hasattr — field added in pal-agents catering migration)
        if (
            hasattr(pal_output, "catering_details")
            and pal_output.catering_details  # type: ignore[reportAttributeAccessIssue]
        ):
            cd = pal_output.catering_details  # type: ignore[reportAttributeAccessIssue]
            logger.info(
                "[catering_details]Catering request received",
                extra={
                    "event_type": "catering_request_placed",
                    "conversation_id": str(conversation_id),
                    "agent_id": str(agent_id),
                    "account_name": account_name,
                    "event_date": cd.event_date,
                    "party_size": cd.party_size,
                    "contact_name": cd.contact_name,
                },
            )
            await _persist_catering_details_from_agent(
                session=session,
                project_id=project_id,
                conversation_id=conversation_id,
                cd=cd,
            )

        if (
            hasattr(pal_output, "checkout_request")
            and pal_output.checkout_request  # type: ignore[reportAttributeAccessIssue]
            and _is_toast_checkout_request(pal_output.checkout_request)  # type: ignore[reportAttributeAccessIssue]
        ):
            logger.info(
                "[ToastCheckout] Checkout request received from pal-agents",
                extra={
                    "conversation_id": str(conversation_id),
                    "agent_id": str(agent_id),
                    "account_name": account_name,
                },
            )
            _schedule_toast_checkout_request(
                checkout_request=pal_output.checkout_request,  # type: ignore[reportAttributeAccessIssue]
                conversation_id=conversation_id,
                sender_identifier=message.recipient_identifier,
                recipient_identifier=message.sender_identifier,
                broker=message.broker,
            )

        # Collect generic tool call events
        if hasattr(pal_output, "events") and pal_output.events:  # type: ignore[reportAttributeAccessIssue]
            collected_events = [
                event
                for event in pal_output.events  # type: ignore[reportAttributeAccessIssue]
                if isinstance(event, dict) and event.get("type") != "sms_followup"
            ]
            logger.info(
                "[tool_call_events] Collected %d events from pal-agents output",
                len(collected_events),
                extra={
                    "event_count": len(collected_events),
                    "conversation_id": str(conversation_id),
                },
            )
            _schedule_tool_result_cache_writes(conversation_id, collected_events)

        output = Output(
            content=pal_output.content,
            escalated=pal_output.escalated,
            closing_conversation=pal_output.closing_conversation,
        )
    else:
        # EXISTING FLOW: Use current agent system
        config = await agent_service.construct_agent_config(
            session=session,
            agent_id=agent_id,
            user_id=user_id,
            project_id=project_id,
            conversation_id=conversation_id,
            channel=message.channel,
            sender_identifier=message.sender_identifier,
            receiver_identifier=message.recipient_identifier,
        )

        agent = Agent(config=config)

        input = await _utils.get_agent_input_from_message(
            message=message,
            stream=False,
            request_context=request_context,
        )
        output: Output = await agent.arun(input)  # type: ignore

    return output, collected_events


async def get_chat_response_async(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    context_modifier: Callable[[RuntimeContext], None] | None = None,
    spec_modifier: Callable[[Spec], None] | None = None,
) -> list[Message]:
    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    try:
        # ==== Step 1: Get project, user, and save request message ====
        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        # Store project attributes early while object is attached to session
        project_id = project.id
        project_name = project.name
        project_raw_config = project.raw_config or {}
        project_agent_id = project.agent_id
        project_account_id = project.account_id
        project_timezone = project.timezone
        project_business_hours = getattr(project, "business_hours", None)
        project_store_hours = getattr(project, "store_hours", None)

        # Check if project uses pal-agents framework (from raw_config)
        use_pal_agents = project_raw_config.get("use_pal_agents", False)

        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )
        if user is None:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id,
            project_id=project_id,
            message_body=message.to_dict(),
            channel=message.channel.value if message.channel else "unknown",
        )

        # Get account info for metadata
        await session.refresh(user, attribute_names=["id"])
        await session.refresh(project, attribute_names=["account"])
        account_name = project.account.name
        testing = (
            getattr(message.metadata, "testing", False) if message.metadata else False
        )

        if not request_message:
            raise ValueError("Failed to create request message")

        # Capture scalar IDs before downstream order persistence can commit the
        # async session and expire ORM attributes.
        user_id = user.id
        request_conversation_id = request_message.conversation_id

        # Get agent_id (needed for metadata regardless of which flow)
        agent_id = project_agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")

        # **************** Step 2: Construct agent, get input, and generate output ****************
        current_message = message.text.body if message.text else ""
        with langfuse_message_span(
            conversation_id=request_conversation_id,
            user_id=user_id,
            agent_id=agent_id,
            account_name=account_name,
            project_name=project_name,
            channel=message.channel.value if message.channel else "unknown",
        ) as lf:
            lf.set_current_trace_io(input={"content": current_message})
            output, collected_events_sync = await _dispatch_agent_async(
                session=session,
                message=message,
                request_context=request_context,
                use_pal_agents=use_pal_agents,
                agent_id=agent_id,
                user_id=user_id,
                project_id=project_id,
                project_account_id=project_account_id,
                project_raw_config=project_raw_config,
                project_timezone=project_timezone,
                project_business_hours=project_business_hours,
                project_store_hours=project_store_hours,
                account_name=account_name,
                conversation_id=request_conversation_id,
                context_modifier=context_modifier,
                spec_modifier=spec_modifier,
            )
            lf.set_current_trace_io(output={"content": output.content})

        # Fire background fingerprinting (covers both pal-agents and legacy flows)
        fp_task = asyncio.create_task(
            _fingerprint_conversation(
                agent_id=agent_id,
                project_id=project_id,
                user_id=user_id,
                conversation_id=request_conversation_id,
                channel=message.channel,
            )
        )
        _background_tasks.add(fp_task)
        fp_task.add_done_callback(_background_tasks.discard)

        # ================ Step 3: Get response messages ================
        # Check if output.content contains a link and create additional SMS response if message.channel is VOICE
        output_message_metadata = Metadata(
            account_name=account_name,
            project_name=project_name,
            agent_id=str(agent_id),
            user_id=str(user_id),
            session_id=str(request_conversation_id),
            testing=testing,
        )

        # Get opt-in message and append to list of messages if applicable
        if is_new_sms_user:
            opt_in_message = build_opt_in_message(message, output_message_metadata)
            if opt_in_message:
                if user:
                    # Save the opt-in message to the database
                    await message_repo.create_message(
                        user_id=user_id,
                        project_id=project_id,
                        message_body=opt_in_message.to_dict(),
                        channel=(
                            opt_in_message.channel.value
                            if opt_in_message.channel
                            else "unknown"
                        ),
                    )

                    await session.refresh(user, attribute_names=["id"])
                response_messages.append(opt_in_message)

        # Get output messages from agent output
        output_messages = _utils.get_messages_from_agent_output(
            output=output, input_message=message, metadata=output_message_metadata
        )

        # Check if messages need to be split into multiple messages using <BREAK> token
        final_output_messages = []
        for message in output_messages:
            if not message.text:
                logger.error(f"Message {message} text is None, skipping message.")
                continue

            split_texts = message.text.body.split("<BREAK>")

            for text in split_texts:
                sub_message = message.model_copy(deep=True)
                sub_message.text = TextObject(body=text.strip())
                final_output_messages.append(sub_message)

        for i, message in enumerate(final_output_messages):
            # Append response message to list of response messages
            response_messages.append(message)
            # Save response message to database
            message_body = message.to_dict()
            if i == 0 and collected_events_sync:
                message_body["tool_calls"] = collected_events_sync
                logger.info(
                    "[tool_call_events] Attached %d events to message body",
                    len(collected_events_sync),
                    extra={
                        "event_count": len(collected_events_sync),
                        "conversation_id": str(request_conversation_id),
                    },
                )
            await message_repo.create_message(
                user_id=user_id,
                project_id=project_id,
                message_body=message_body,
                channel=message.channel.value if message.channel else "unknown",
            )

        await session.refresh(user, attribute_names=["id"])
        await session.refresh(request_message, attribute_names=["conversation_id"])

        # Make sure to handle the case after the response messages are created
        # Check if output.closing_conversation is True and mark the conversation as closing
        if output.closing_conversation:
            conversation = await db.ConversationRepositoryAsync(
                session
            ).get_conversation_by_id(conversation_id=request_conversation_id)
            if conversation:
                conversation.status = db.ConversationStatus.CLOSING
                await session.flush()

    except Exception as e:
        logger.exception("Error in get_chat_response_async")
        raise e

    return response_messages


async def get_chat_response_stream(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    call_id: str | None = None,
    room_name: str | None = None,
    participant_identity: str | None = None,
    sip_provider: str | None = None,
    language: str | None = None,
    event_collector: Callable[[dict[str, Any]], None] | None = None,
    framework_collector: Callable[[str], None] | None = None,
) -> AsyncIterator[ChatCompletionChunk]:
    async with trace_async_block("Message Service Stream Processing"):
        message_repo = db.MessageRepositoryAsync(session)
        stream_id = f"chatcmpl-{uuid.uuid4().hex}"

        try:
            # ==== Step 1: Get project, user, and save request message ====
            project = await project_service.get_project_async(session, message)
            # Capture project attributes early while object is attached to session
            project_id = project.id
            project_name = project.name
            project_raw_config = project.raw_config or {}
            project_agent_id = project.agent_id
            project_account_id = project.account_id
            project_timezone = project.timezone
            project_business_hours = getattr(project, "business_hours", None)
            project_store_hours = getattr(project, "store_hours", None)

            # Check if project uses pal-agents framework (from raw_config)
            use_pal_agents = project_raw_config.get("use_pal_agents", False)
            if framework_collector:
                try:
                    framework_collector("pal_agents" if use_pal_agents else "agno")
                except Exception:
                    logger.exception(
                        "framework_collector callback failed; continuing stream setup"
                    )

            user, is_new_sms_user = await user_service.get_user_async(
                session, project, message
            )

            if is_new_sms_user:
                raise ValueError("Stream mode should be only for voice mode")

            if user is None:
                user = await user_service.create_user_async(session, project, message)
            await session.refresh(user, attribute_names=["id"])

            # Capture user_id early while object is attached to session
            # (prevents MissingGreenlet errors after commits expire the object)
            user_id = user.id

            # For VOICE channel with call_id, use voice-specific message creation
            # to reuse the conversation created during handle_assistant_request
            if message.channel == Channel.VOICE and call_id:
                request_message = await message_repo.add_message_to_voice_conversation(
                    user_id=user_id,
                    message_body=message.to_dict(),
                    call_id=call_id,
                )
            else:
                # Warn if voice message is missing call_id - this shouldn't happen
                if message.channel == Channel.VOICE and not call_id:
                    logger.warning(
                        "[get_chat_response_stream] Voice message missing call_id, "
                        "falling back to text message conversation logic",
                        extra={
                            "user_id": str(user_id),
                            "project_id": str(project_id),
                            "sender_identifier": message.sender_identifier,
                            "recipient_identifier": message.recipient_identifier,
                        },
                    )
                # Existing text message logic with conversation reuse
                request_message = await message_repo.create_message(
                    user_id=user_id,
                    project_id=project_id,
                    message_body=message.to_dict(),
                    channel=message.channel.value if message.channel else "unknown",
                )

            if not request_message:
                raise ValueError("Failed to create request message")

            # Capture conversation_id early while object is attached to session
            request_conversation_id = request_message.conversation_id

            # Get account info for metadata
            await session.refresh(user, attribute_names=["id"])
            await session.refresh(project, attribute_names=["account", "agent"])
            account_name = project.account.name
            testing = (
                getattr(message.metadata, "testing", False)
                if message.metadata
                else False
            )

            # ==== Step 2: Set up agent and generate streaming response ====
            agent_id = project_agent_id
            if agent_id is None:
                raise ValueError("Agent ID not found")

            collected_content: list[str] = []
            collected_events: list[dict] = []
            current_message = ""

            with langfuse_message_span(
                conversation_id=request_conversation_id,
                user_id=user_id,
                agent_id=agent_id,
                account_name=account_name,
                project_name=project_name,
                channel=message.channel.value if message.channel else "unknown",
            ) as lf:
                lf.set_current_trace_io(
                    input={"content": message.text.body if message.text else ""},
                )

                # ========== CHUNK GENERATION (if/else by project config) ==========
                if use_pal_agents:
                    # PAL-AGENTS PATH

                    spec = await agent_service.construct_agent_spec(
                        session=session,
                        agent_id=agent_id,
                        user_id=user_id,
                        project_id=project_id,
                        conversation_id=request_conversation_id,
                        channel=message.channel,
                        sender_identifier=message.sender_identifier,
                        raw_config=project_raw_config,
                        room_name=room_name,
                        participant_identity=participant_identity,
                        language=language,
                        sip_provider=sip_provider,
                    )
                    # Auto-harden Spec when the conversation is a test /
                    # eval run. See ``_apply_test_safety_if_needed``.
                    await _apply_test_safety_if_needed(
                        session, request_conversation_id, spec
                    )
                    customer_phone = None
                    if message.channel and message.channel.value.lower() in [
                        "sms",
                        "voice",
                        "whatsapp",
                    ]:
                        customer_phone = message.sender_identifier

                    await _attach_prior_catering_requests_to_spec(
                        session, spec, project_id, customer_phone
                    )

                    pal_agent = PalAgent(spec=spec)

                    # Pre-fetch voice-specific data for RuntimeContext
                    vapi_control_url = None
                    if message.channel == Channel.VOICE and call_id:
                        try:
                            conversation = await db.ConversationRepositoryAsync(
                                session
                            ).get_conversation_by_id(
                                conversation_id=request_conversation_id
                            )
                            vapi_control_url = conversation.vapi_control_url
                        except Exception as e:
                            # Catch all exceptions for graceful degradation during voice calls.
                            # Voice transfer tools can function without this URL if needed.
                            logger.warning(
                                "Failed to fetch conversation for vapi_control_url: %s",
                                str(e),
                                extra={
                                    "conversation_id": str(request_conversation_id),
                                    "call_id": call_id,
                                    "exception_type": type(e).__name__,
                                },
                            )

                    store_status = compute_store_status(
                        project_business_hours,
                        project_store_hours,
                        project_timezone,
                    )

                    runtime_context = RuntimeContext(
                        user_id=str(user_id),
                        session_id=str(request_conversation_id),
                        customer_phone=customer_phone,
                        project_id=str(project_id),
                        account_id=str(project_account_id),
                        account_name=account_name,
                        agent_id=str(agent_id),
                        timezone=project_timezone or "America/Los_Angeles",
                        channel=message.channel.value,
                        store_status=store_status,
                        # Voice-specific fields (extra="allow" permits these)
                        call_id=call_id,  # type: ignore[call-arg]
                        vapi_control_url=vapi_control_url,  # type: ignore[call-arg]
                        room_name=room_name,  # type: ignore[call-arg]
                        participant_identity=participant_identity,  # type: ignore[call-arg]
                    )

                    await _hydrate_previous_tool_results(
                        runtime_context,
                        request_conversation_id,
                    )

                    # Fetch and format conversation history (same as non-streaming)
                    history_messages = await query_history_messages(
                        request_conversation_id,
                        limit=100,
                    )

                    current_message = message.text.body if message.text else ""
                    history_text = ""
                    if history_messages:
                        if (
                            history_messages[-1].content == current_message
                            and history_messages[-1].role == "user"
                        ):
                            prior_messages = history_messages[:-1]
                        else:
                            logger.warning(
                                "[pal-agents streaming] Last history message does not match current input. "
                                f"Expected: {current_message[:50]}..., "
                                f"Got: {(history_messages[-1].content or '')[:50]}..."
                            )
                            prior_messages = history_messages

                        if prior_messages:
                            history_text = "\n".join(
                                [
                                    f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content}"
                                    for msg in prior_messages
                                    if msg.content  # Filter out None/empty content
                                ]
                            )

                    if history_text:
                        full_content = (
                            f"<conversation_history>\n{history_text}\n</conversation_history>\n\n"
                            f"User: {current_message}"
                        )
                    else:
                        full_content = f"User: {current_message}"

                    pal_input = PalInput(
                        content=full_content,
                        runtime_context=runtime_context,
                    )

                    record_duration(
                        "message.streaming.start.duration",
                        request_context.request_time,
                        attributes={
                            "agent_id": str(agent_id),
                        },
                    )

                    # Stream from pal-agents
                    async with trace_async_block("Message Service Streaming"):
                        index = 0
                        record_duration(
                            "message.streaming.first_chunk.wait",
                            request_context.request_time,
                            attributes={
                                "agent_id": str(agent_id),
                            },
                        )

                        transfer_purpose_captured = None

                        try:
                            pal_stream = await pal_agent.run(pal_input, stream=True)
                            if pal_stream is None:
                                # Gracefully stop streaming when upstream cancellation/teardown
                                # results in a missing iterator from pal-agents.
                                logger.warn(
                                    "[MessageService] pal-agents stream unavailable, ending stream",
                                    extra={
                                        "agent_id": str(agent_id),
                                        "conversation_id": str(request_conversation_id),
                                    },
                                )
                                return
                            if not hasattr(pal_stream, "__aiter__"):
                                raise TypeError(
                                    "Expected async iterator from pal_agent.run(stream=True), "
                                    f"got {type(pal_stream).__name__}"
                                )

                            async for chunk in pal_stream:
                                if index == 0:
                                    record_duration(
                                        "message.streaming.first_chunk.duration",
                                        request_context.request_time,
                                        attributes={
                                            "agent_id": str(agent_id),
                                        },
                                    )

                                # Capture and persist transfer_purpose immediately (before cancellation can interrupt)
                                if (
                                    hasattr(chunk, "transfer_purpose")
                                    and chunk.transfer_purpose
                                    and not transfer_purpose_captured  # Only persist once
                                ):
                                    transfer_purpose_captured = chunk.transfer_purpose
                                    try:
                                        conversation = (
                                            await db.ConversationRepositoryAsync(
                                                session
                                            ).get_conversation_by_id(
                                                conversation_id=request_conversation_id
                                            )
                                        )
                                        if conversation:
                                            conversation.transfer_purpose = (
                                                transfer_purpose_captured
                                            )
                                            await session.commit()
                                            logger.info(
                                                "Captured transfer_purpose during streaming",
                                                extra={
                                                    "conversation_id": str(
                                                        request_conversation_id
                                                    ),
                                                    "transfer_purpose": transfer_purpose_captured,
                                                },
                                            )
                                    except Exception as e:
                                        await session.rollback()
                                        logger.warning(
                                            "Failed to persist transfer_purpose",
                                            extra={
                                                "conversation_id": str(
                                                    request_conversation_id
                                                ),
                                                "error": str(e),
                                            },
                                        )

                                # Persist order_details if present in streaming response
                                if (
                                    hasattr(chunk, "order_details")
                                    and chunk.order_details
                                ):
                                    order_details = chunk.order_details
                                    logger.info(
                                        "[order_details]Order details received in streaming response",
                                        extra={
                                            "event_type": "order_details_streamed",
                                            "conversation_id": str(
                                                request_conversation_id
                                            ),
                                            "agent_id": str(agent_id),
                                            "account_name": account_name,
                                            "vendor": order_details.vendor,
                                            "order_id": order_details.order_id,
                                            "store_id": order_details.store_id,
                                            "user_phone_number": order_details.user_phone_number,
                                            "tracking_link": order_details.tracking_link,
                                            "status": order_details.status,
                                            "fulfillment_strategy": order_details.fulfillment_strategy,
                                            "subtotal": float(order_details.subtotal),
                                            "tax": float(order_details.tax),
                                            "service_charge": float(
                                                order_details.service_charge
                                            ),
                                            "delivery_charge": float(
                                                order_details.delivery_charge
                                            ),
                                            "discount": float(order_details.discount),
                                            "total": float(order_details.total),
                                            "item_count": len(
                                                order_details.order_items
                                            ),
                                            "order_time": order_details.order_time,
                                        },
                                    )

                                    # Persist order to database using transaction service
                                    await transaction_service.create_order_from_agent_async(
                                        session=session,
                                        order_details=order_details,
                                        conversation_id=request_conversation_id,
                                    )

                                # Persist reservation_details if present in streaming response
                                if (
                                    hasattr(chunk, "reservation_details")
                                    and chunk.reservation_details
                                ):
                                    rd = chunk.reservation_details
                                    logger.info(
                                        "[reservation_details]Reservation/waitlist received in stream",
                                        extra={
                                            "event_type": "reservation_placed_streamed",
                                            "conversation_id": str(
                                                request_conversation_id
                                            ),
                                            "agent_id": str(agent_id),
                                            "account_name": account_name,
                                            "vendor": rd.vendor,
                                            "entry_type": rd.entry_type,
                                            "reservation_id": rd.reservation_id,
                                            "store_id": rd.store_id,
                                            "status": rd.status,
                                            "party_size": rd.party_size,
                                        },
                                    )
                                    await reservation_service.save_reservation_from_agent_async(
                                        session=session,
                                        reservation_details=rd,
                                        conversation_id=request_conversation_id,
                                    )

                                # Persist catering_details if present in streaming response
                                # (guarded by hasattr — field added in pal-agents catering migration)
                                if (
                                    hasattr(chunk, "catering_details")
                                    and chunk.catering_details  # type: ignore[reportAttributeAccessIssue]
                                ):
                                    cd = chunk.catering_details  # type: ignore[reportAttributeAccessIssue]
                                    logger.info(
                                        "[catering_details]Catering request received in stream",
                                        extra={
                                            "event_type": "catering_request_placed_streamed",
                                            "conversation_id": str(
                                                request_conversation_id
                                            ),
                                            "agent_id": str(agent_id),
                                            "account_name": account_name,
                                            "event_date": cd.event_date,
                                            "party_size": cd.party_size,
                                            "contact_name": cd.contact_name,
                                        },
                                    )
                                    await _persist_catering_details_from_agent(
                                        session=session,
                                        project_id=project_id,
                                        conversation_id=request_conversation_id,
                                        cd=cd,
                                    )

                                if (
                                    hasattr(chunk, "checkout_request")
                                    and chunk.checkout_request  # type: ignore[reportAttributeAccessIssue]
                                    and _is_toast_checkout_request(chunk.checkout_request)  # type: ignore[reportAttributeAccessIssue]
                                ):
                                    logger.info(
                                        "[ToastCheckout] Checkout request received in stream",
                                        extra={
                                            "conversation_id": str(
                                                request_conversation_id
                                            ),
                                            "agent_id": str(agent_id),
                                            "account_name": account_name,
                                        },
                                    )
                                    _schedule_toast_checkout_request(
                                        checkout_request=chunk.checkout_request,  # type: ignore[reportAttributeAccessIssue]
                                        conversation_id=request_conversation_id,
                                        sender_identifier=message.recipient_identifier,
                                        recipient_identifier=message.sender_identifier,
                                        broker=message.broker,
                                    )

                                # Collect generic tool call events
                                # (guarded by hasattr — field added in pal-agents feat/generic-tool-call-events)
                                if hasattr(chunk, "events") and chunk.events:  # type: ignore[reportAttributeAccessIssue]
                                    chunk_events = [
                                        event
                                        for event in chunk.events  # type: ignore[reportAttributeAccessIssue]
                                        if isinstance(event, dict)
                                    ]
                                    persistable_events = []
                                    for event in chunk_events:
                                        if event.get("type") == "sms_followup":
                                            if event_collector:
                                                event_collector(event)
                                        else:
                                            persistable_events.append(event)

                                    collected_events.extend(persistable_events)
                                    _schedule_tool_result_cache_writes(
                                        request_conversation_id,
                                        persistable_events,
                                    )
                                    logger.info(
                                        "[tool_call_events] Collected %d events from stream chunk",
                                        len(persistable_events),
                                        extra={
                                            "event_count": len(persistable_events),
                                            "total_events": len(collected_events),
                                            "conversation_id": str(
                                                request_conversation_id
                                            ),
                                        },
                                    )

                                if not chunk.content:
                                    continue

                                completion_chunk = ChatCompletionChunk(
                                    id=stream_id,
                                    object="chat.completion.chunk",
                                    created=int(
                                        datetime.datetime.now(
                                            datetime.timezone.utc
                                        ).timestamp()
                                    ),
                                    model=message.recipient_identifier,
                                    choices=[
                                        ChunkChoice(
                                            index=0,
                                            delta=ChoiceDelta(
                                                role="assistant", content=chunk.content
                                            ),
                                            finish_reason=None,
                                        )
                                    ],
                                )
                                yield completion_chunk
                                collected_content.append(chunk.content)
                                index += 1
                        except asyncio.CancelledError:
                            logger.debug("[MessageService] pal-agents stream cancelled")
                            return
                        except RuntimeError as stream_error:
                            # Async generator wrappers (e.g. tracing middleware) can convert
                            # normal StopAsyncIteration completion into a RuntimeError.
                            if (
                                isinstance(stream_error.__cause__, StopAsyncIteration)
                                or str(stream_error)
                                == "async generator raised StopAsyncIteration"
                            ):
                                logger.debug(
                                    "pal-agents stream ended with wrapped StopAsyncIteration",
                                    extra={
                                        "agent_id": str(agent_id),
                                        "conversation_id": str(request_conversation_id),
                                        "error": str(stream_error),
                                        "error_type": type(stream_error).__name__,
                                        "cause": str(stream_error.__cause__),
                                        "cause_type": (
                                            type(stream_error.__cause__).__name__
                                            if stream_error.__cause__
                                            else None
                                        ),
                                    },
                                )
                            else:
                                raise
                        finally:
                            pass  # transfer_purpose already persisted during streaming

                else:
                    # LEGACY PATH - existing agent system
                    config = await agent_service.construct_agent_config(
                        session=session,
                        agent_id=agent_id,
                        user_id=user_id,
                        project_id=project_id,
                        conversation_id=request_conversation_id,
                        channel=message.channel,
                        sender_identifier=message.sender_identifier,
                        receiver_identifier=message.recipient_identifier,
                        room_name=room_name,
                        participant_identity=participant_identity,
                        sip_provider=sip_provider,
                    )
                    config.stream = True

                    agent = Agent(config=config)

                    input = await _utils.get_agent_input_from_message(
                        message=message,
                        stream=True,
                        request_context=request_context,
                    )
                    record_duration(
                        "message.streaming.start.duration",
                        request_context.request_time,
                        attributes={
                            "agent_id": str(agent_id),
                        },
                    )

                    response_stream: AsyncIterator[Output] = await agent.arun(input)  # type: ignore

                    if response_stream:
                        async with trace_async_block("Message Service Streaming"):
                            index = 0
                            record_duration(
                                "message.streaming.first_chunk.wait",
                                request_context.request_time,
                                attributes={
                                    "agent_id": str(agent_id),
                                },
                            )

                            async for chunk in response_stream:
                                if index == 0:
                                    record_duration(
                                        "message.streaming.first_chunk.duration",
                                        request_context.request_time,
                                        attributes={
                                            "agent_id": str(agent_id),
                                        },
                                    )

                                async with trace_async_block(
                                    "Process Stream Chunk",
                                    tags={
                                        "chunk_index": index,
                                        "conversation_id": str(request_conversation_id),
                                        "chunk_type": type(chunk).__name__,
                                    },
                                ) as span:
                                    # Process different chunk types into content string
                                    content = ""
                                    if isinstance(chunk, Output):
                                        content = chunk.content
                                        # Check for conversation closing if available
                                        if (
                                            hasattr(chunk, "closing_conversation")
                                            and chunk.closing_conversation
                                        ):
                                            conversation = await db.ConversationRepositoryAsync(
                                                session
                                            ).get_conversation_by_id(
                                                conversation_id=request_conversation_id
                                            )
                                            if conversation:
                                                conversation.status = (
                                                    db.ConversationStatus.CLOSING
                                                )
                                                await session.flush()
                                    elif isinstance(chunk, RunResponse):
                                        content = chunk.get_content_as_string()
                                    elif isinstance(chunk, tuple):
                                        content = chunk[0]
                                    elif isinstance(chunk, Message):
                                        content = chunk.text.body if chunk.text else ""
                                    elif chunk:
                                        if not isinstance(
                                            chunk, (str, int, float, bool)
                                        ):
                                            logger.warning(
                                                f"Unexpected chunk type: {type(chunk)}"
                                            )
                                            continue
                                        content = str(chunk)

                                    # Skip empty chunks
                                    if not content:
                                        continue

                                    # Update span tags with content (skip if span is None in testing mode)
                                    if span:
                                        span.set_attribute(
                                            "content",
                                            (
                                                content[:100]
                                                if len(content) > 100
                                                else content
                                            ),
                                        )

                                    # Create and yield chunk
                                    completion_chunk = ChatCompletionChunk(
                                        id=stream_id,
                                        object="chat.completion.chunk",
                                        created=int(
                                            datetime.datetime.now(
                                                datetime.timezone.utc
                                            ).timestamp()
                                        ),
                                        model=message.recipient_identifier,
                                        choices=[
                                            ChunkChoice(
                                                index=0,
                                                delta=ChoiceDelta(
                                                    role="assistant", content=content
                                                ),
                                                finish_reason=None,
                                            )
                                        ],
                                    )
                                    yield completion_chunk
                                    # Store original content for relay service
                                    collected_content.append(content)
                                    index += 1

                # ==== Step 4: After streaming, save final messages to database ====
                # (shared by both pal-agents and legacy paths)
                if collected_content:
                    output_message_metadata = Metadata(
                        account_name=account_name,
                        project_name=project_name,
                        agent_id=str(agent_id),
                        user_id=str(user_id),
                        session_id=str(request_conversation_id),
                        testing=testing,
                    )

                    full_response = "".join(collected_content)

                    response_message = Message(
                        author_type=AuthorType.AGENT,
                        sender_identifier=message.recipient_identifier,
                        recipient_identifier=message.sender_identifier,
                        channel=message.channel,
                        broker=message.broker,
                        channel_info=message.channel_info,
                        text=TextObject(body=full_response),
                        metadata=output_message_metadata,
                    )

                    # Use add_message_to_conversation with the known conversation_id
                    # instead of create_message which does a lookup that can find
                    # the wrong conversation when multiple active conversations exist
                    response_message_body = response_message.to_dict()
                    if collected_events:
                        response_message_body["tool_calls"] = collected_events
                        logger.info(
                            "[tool_call_events] Attached %d events to streaming message body",
                            len(collected_events),
                            extra={
                                "event_count": len(collected_events),
                                "conversation_id": str(request_conversation_id),
                            },
                        )

                    await message_repo.add_message_to_conversation(
                        conversation_id=request_conversation_id,
                        message_body=response_message_body,
                    )

                    await session.refresh(user, attribute_names=["id"])

                if collected_content:
                    lf.set_current_trace_io(
                        output={"content": "".join(collected_content)},
                    )

        except asyncio.CancelledError:
            logger.debug("[MessageService] Stream cancelled (client disconnect)")
            return

        except Exception as e:
            # Log error and return a single error chunk
            logger.exception(f"Error in get_chat_response_stream: {e}")
            error_message = ChatCompletionChunk(
                id=stream_id,
                object="chat.completion.chunk",
                created=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                model=message.recipient_identifier if message else "unknown",
                choices=[
                    ChunkChoice(
                        index=0,
                        delta=ChoiceDelta(role="assistant", content=""),
                        finish_reason="stop",  # Using a valid finish_reason value
                    )
                ],
            )
            yield error_message


def get_chat_response(_session: Session, message: Message) -> Message:
    response = "Synch mode chat has been deprecated."
    response_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
        recipient_identifier=message.sender_identifier,
        channel=message.channel,
        broker=message.broker,
        channel_info=message.channel_info,
        text=TextObject(body=response),
    )

    return response_message


def get_message_by_id(session: Session, message_id: uuid.UUID) -> db.Message | None:
    """
    Retrieves a Message by its unique identifier.

    This function queries the database to fetch the Message associated with the specified Message ID.

    Args:
        session (Session): The database connection.
        message_id (uuid.UUID): The unique identifier of the Message being retrieved.

    Returns:
        db.Message | None: The Message object associated with the unique identifier, or None if not found.
    """
    message = db.MessageRepository(session).get_message_by_id(message_id=message_id)
    return message


def get_messages_by_ids(
    session: Session, message_ids: list[uuid.UUID]
) -> list[db.Message]:
    messages = db.MessageRepository(session).get_messages_by_ids(
        message_ids=message_ids
    )
    return messages


def get_messages_by_conversation(
    session: Session, conversation_id: uuid.UUID
) -> list[db.Message]:
    """
    Retrieves all Messages for a given Conversation.

    This function queries the database to fetch all Messages associated with the specified Conversation ID.

    Args:
        session (Session): The database connection.
        conversation_id (uuid.UUID): The unique identifier of the Conversation for which Messages are being retrieved.

    Returns:
        list[db.Message]: A list of Message objects representing the messages in the specified Conversation.
    """
    messages = db.MessageRepository(session).get_messages_by_conversation(
        conversation_id=conversation_id
    )
    return messages


def get_conversations_by_user(
    session: Session, user_id: uuid.UUID, create_new_conversation: bool = False
) -> list[db.Conversation]:
    conversation_repository = db.ConversationRepository(session)
    conversations = conversation_repository.get_conversations_by_user(
        user_id=user_id,
    )

    if conversations:
        return conversations

    if create_new_conversation:
        new_conversation = conversation_repository.create_conversation(user_id=user_id)
        return [new_conversation] if new_conversation else []

    return []


def get_conversations_by_users(
    session: Session,
    page: int,
    page_size: int,
    user_ids: list[uuid.UUID],
) -> tuple[int, list[db.Conversation]]:
    conversation_repository = db.ConversationRepository(session)
    conversations, total_conversations = (
        conversation_repository.get_conversations_by_users(
            page=page,
            page_size=page_size,
            user_ids=user_ids,
        )
    )
    return total_conversations, conversations


def create_conversation(
    session: Session,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    channel: Channel | None = None,
) -> db.Conversation | None:
    conversation_repository = db.ConversationRepository(session)
    conversation = conversation_repository.create_conversation(user_id=user_id)

    if not conversation:
        logger.error(f"Failed to create conversation for user {user_id}")
        return None

    return conversation


async def create_voice_call_conversation(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    message_body: dict,
    call_id: str,
) -> db.Message:
    """Create a new conversation + initial message for a voice call."""
    message_repo = db.MessageRepositoryAsync(session)
    return await message_repo.create_voice_message(
        user_id=user_id,
        project_id=project_id,
        message_body=message_body,
        call_id=call_id,
    )


def build_opt_in_message(message: Message, metadata: Metadata) -> Message | None:
    if message.broker == Broker.TWILIO and message.channel == Channel.SMS:
        opt_in_text = (
            "You have successfully been subscribed to messages from this number. "
            "Reply STOP to unsubscribe. Msg&Data Rates May Apply."
        )
        return Message(
            author_type=AuthorType.AGENT,
            sender_identifier=message.recipient_identifier,  # Swap sender and recipient
            recipient_identifier=message.sender_identifier,
            channel=message.channel,
            broker=message.broker,
            channel_info=message.channel_info,
            text=TextObject(body=opt_in_text),
            metadata=metadata,
            extras=Extras(),
        )

    return None
