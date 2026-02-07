from fastapi import APIRouter, Request
from starlette.responses import Response

from api.routes.endpoints import endpoints

from ._webhook import handle_voice_webhook

twilio_router = APIRouter(prefix="/twilio", tags=["Integrations"])


@twilio_router.post("/voice")
async def twilio_voice_webhook(request: Request) -> Response:
    """
    Webhook endpoint for Twilio voice calls.

    Called by Twilio when an incoming call is received. Returns TwiML
    that instructs Twilio to connect to our WebSocket endpoint for
    real-time audio streaming.

    Args:
        request: FastAPI request containing call parameters and signature

    Returns:
        TwiML XML response with Stream configuration
    """
    return await handle_voice_webhook(request)
