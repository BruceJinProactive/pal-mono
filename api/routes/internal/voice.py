"""Internal voice initialization endpoint for LiveKit agent worker."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.internal.voice_init import (
    VoiceEndCallRequest,
    VoiceInitRequest,
    VoiceInitResponse,
)

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


@voice_router.post(
    "/end-call",
    status_code=status.HTTP_200_OK,
)
async def end_voice_call(
    request: VoiceEndCallRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    """End a voice call from the LiveKit agent worker.

    Called by the LiveKit agent when a SIP call ends. Logs call details
    and finds the conversation_id associated with the call.
    """
    return await _voice.end_voice_call(request, session)
