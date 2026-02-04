from fastapi import APIRouter, WebSocket

from ._implementation import handle_twilio_media_stream

twilio_router = APIRouter(prefix="/twilio", tags=["Integrations"])


@twilio_router.websocket("/ws")
async def twilio_media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.

    Receives real-time audio streams from Twilio phone calls and logs all events
    to understand the protocol flow.

    Message Types:
    - connected: Initial connection establishment with protocol version
    - start: Stream metadata including callSid, streamSid, accountSid, and media format
    - media: Audio data packets (base64-encoded 8kHz mu-law audio)
    - stop: Stream ended notification

    Args:
        websocket: WebSocket connection from Twilio Media Streams

    Protocol Reference:
        https://www.twilio.com/docs/voice/twiml/stream
    """
    await handle_twilio_media_stream(websocket)
