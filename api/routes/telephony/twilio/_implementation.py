"""Twilio Media Stream WebSocket handler using VoiceCallHandler."""

import json

from fastapi import WebSocket

from db.session import AsyncSessionLocal
from services import realtime_service
from utils.log import logger

from ._voice_handler import VoiceCallHandler


async def handle_twilio_media_stream(websocket: WebSocket):
    """
    Handle Twilio Media Stream WebSocket connection.

    Delegates to VoiceCallHandler for orchestration.

    Args:
        websocket: WebSocket connection from Twilio
    """
    # Accept connection
    await websocket.accept()

    # Wait for 'start' event to get recipient_id
    # (VoiceCallHandler will handle subsequent events)
    realtime_session = None
    handler = None

    try:
        # Receive first message (should be 'connected' or 'start')
        first_message = await websocket.receive_text()
        first_event = json.loads(first_message)

        # Wait for 'start' event if first message was 'connected'
        if first_event.get("event") == "connected":
            start_message = await websocket.receive_text()
            start_event = json.loads(start_message)
        else:
            start_event = first_event

        # Extract recipient_id from start event
        if start_event.get("event") != "start":
            logger.error(
                "[TWILIO_WS] Expected 'start' event, got: "
                + start_event.get("event", "unknown")
            )
            await websocket.close(code=1008, reason="Expected start event")
            return

        start_data = start_event.get("start", {})
        custom_params = start_data.get("customParameters", {})
        recipient_id = custom_params.get("to_number")
        caller_id = custom_params.get("from_number")

        if not recipient_id:
            logger.error("[TWILIO_WS] Missing recipient_id in start event")
            await websocket.close(code=1008, reason="Missing recipient_id")
            return

        logger.info(
            "[TWILIO_WS] Starting call",
            extra={
                "recipient_id": recipient_id,
                "caller_id": caller_id,
                "call_sid": start_data.get("callSid"),
            },
        )

        # Extract call_id from Twilio start event
        call_sid = start_data.get("callSid")

        # Create realtime session
        async with AsyncSessionLocal() as db_session:
            try:
                realtime_session = await realtime_service.create_realtime_session(
                    db_session,
                    recipient_id,
                    caller_id=caller_id,
                    call_id=call_sid,
                )
            except ValueError as e:
                logger.error(f"[TWILIO_WS] Project lookup failed: {e}")
                await websocket.close(code=1008, reason="Project not found")
                return
            except Exception as e:
                logger.error(
                    "[TWILIO_WS] Failed to create realtime session",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                await websocket.close(code=1011, reason="Service unavailable")
                return

        # Create handler and wire interruption callback
        handler = VoiceCallHandler(
            twilio_websocket=websocket,
            realtime_session=realtime_session,
        )
        realtime_session.on_interruption = handler._handle_barge_in

        await handler.handle_call(start_event=start_event)

    except Exception as e:
        logger.error(
            "[TWILIO_WS] Unexpected error",
            extra={"error": str(e)},
            exc_info=True,
        )

    finally:
        # Cleanup: If handler was created, it handles cleanup in its own finally block
        # If handler was NOT created but realtime_session was, we need to clean up here
        if handler is None and realtime_session is not None:
            # Close realtime session
            try:
                await realtime_session.close()
            except Exception as cleanup_error:
                logger.error(
                    "[TWILIO_WS] Error closing realtime session during cleanup",
                    extra={"error": str(cleanup_error)},
                )

            # Close WebSocket
            try:
                await websocket.close()
            except Exception as cleanup_error:
                logger.error(
                    "[TWILIO_WS] Error closing WebSocket during cleanup",
                    extra={"error": str(cleanup_error)},
                )
