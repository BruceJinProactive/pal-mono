from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.endpoints import endpoints
from api.schemas.admin.onboarding import (
    CreateVAPIAssistantRequest,
    DeleteVAPIAssistantResponse,
    VAPIAssistantResponse,
)
from api.schemas.error.error import ErrorResponse
from services.voice_service import VoiceService

from ._implementation import api_vapi_server

vapi_router = APIRouter(prefix="/vapi", tags=["Integrations"])


@vapi_router.post(
    "/",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Successful response"},
        400: {"model": ErrorResponse},
        401: {"description": "Unauthorized"},
        500: {"model": ErrorResponse},
    },
)
async def vapi_server(
    request: Request,
    session: AsyncSession = Depends(db.get_db_async),
) -> JSONResponse:
    """
    Endpoint to be used as VAPI server URL.
    Handles incoming requests from VAPI service according to the VAPI Server Events specification.

    Handles the following event types:
    - assistant-request: when a call starts
    - status-update: when call status changes
    - function-call: when Assistant calls a function
    - transcript-update: when new transcripts are available
    """
    return await api_vapi_server(request, session)


# VAPI Assistant Management Endpoints


@vapi_router.post(
    "/assistants",
    response_model=VAPIAssistantResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Assistant created successfully"},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_vapi_assistant(
    create_request: CreateVAPIAssistantRequest,
) -> VAPIAssistantResponse:
    """
    Create a new VAPI assistant.

    This endpoint creates a new assistant with the provided configurable fields:
    - name: Assistant name
    - firstMessage: Optional greeting message
    - maxDurationSeconds: Optional call duration limit
    - systemPrompt: System prompt for the AI model
    - voiceId: Voice ID for speech synthesis

    Fixed configuration:
    - Transcriber: Deepgram with en-US language
    - Model: OpenAI GPT-4o with temperature 0.7
    - Voice Provider: Cartesia
    """
    voice_service = VoiceService()
    return await voice_service.create_vapi_assistant(create_request)


@vapi_router.get(
    "/assistants/{assistant_id}",
    response_model=VAPIAssistantResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Assistant retrieved successfully"},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_vapi_assistant(
    assistant_id: str,
) -> VAPIAssistantResponse:
    """
    Get a VAPI assistant by ID.

    Retrieves the configuration and details of a specific VAPI assistant.
    """
    voice_service = VoiceService()
    return await voice_service.get_vapi_assistant(assistant_id)


@vapi_router.delete(
    "/assistants/{assistant_id}",
    response_model=DeleteVAPIAssistantResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Assistant deleted successfully"},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_vapi_assistant(
    assistant_id: str,
) -> DeleteVAPIAssistantResponse:
    """
    Delete a VAPI assistant.

    Permanently deletes a VAPI assistant and all its configurations.
    This action cannot be undone.
    """
    voice_service = VoiceService()
    return await voice_service.delete_vapi_assistant(assistant_id)
