"""Internal voice initialization endpoint for LiveKit agent worker."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.internal.voice_init import VoiceInitRequest, VoiceInitResponse

from . import _voice

voice_router = APIRouter(prefix="/voice", tags=["internal-voice"])


@voice_router.post(
    "/init",
    status_code=status.HTTP_200_OK,
)
async def init_voice_call(
    request: VoiceInitRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> VoiceInitResponse:
    """Initialize a voice call for the LiveKit agent worker.

    Called by the LiveKit agent when a SIP call arrives. Creates a conversation,
    resolves the project and user, and returns voice configuration for the
    agent session (STT, TTS, LLM proxy settings).
    """
    return await _voice.init_voice_call(request, session)
