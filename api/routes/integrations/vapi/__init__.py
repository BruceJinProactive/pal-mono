from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse
from db.tables.types import SpeechRate

from ._implementation import api_vapi_server, handle_create_vapi_assistant


class VoiceConfig(BaseModel):
    """Voice configuration for VAPI assistant."""

    model_config = {"populate_by_name": True}

    provider: str = Field(..., description="Voice provider (e.g., 'cartesia')")
    model: str = Field(..., description="Voice model (e.g., 'sonic-2')")
    voiceId: str = Field(..., description="Voice ID for speech synthesis")
    speech_rate: SpeechRate = Field(
        SpeechRate.normal,
        alias="speechRate",
        description="Speech rate enum (slowest, slower, normal, faster, fastest)",
    )


class CreateVapiAssistantRequest(BaseModel):
    """Request model for creating a VAPI assistant."""

    name: str = Field(..., description="Assistant name")
    firstMessage: str | None = Field(None, description="Optional greeting message")
    maxDurationSeconds: int | None = Field(
        None, description="Optional call duration limit in seconds"
    )
    systemPrompt: str = Field(..., description="System prompt for the AI model")
    voice: VoiceConfig = Field(
        ..., description="Voice configuration from admin console"
    )
    languageGroups: list[list[str]] = Field(
        ...,
        description=(
            "Language groups for assistant creation. "
            "Single group with one language (e.g., [['English']]) creates a single-language assistant. "
            "Single group with multiple languages (e.g., [['English', 'Chinese']]) creates a single multilingual assistant. "
            "Multiple groups (e.g., [['English'], ['Chinese']]) creates a squad with triage and separate assistants per group."
        ),
    )
    transcribers: list[dict] | None = Field(
        None,
        description=(
            "List of transcriber configurations, one per language group. "
            "Each transcriber contains provider, model, language, and other settings. "
            "Must have same length as languageGroups if provided. "
            "Required for non-English assistants. "
            "For English-only assistants, defaults to Deepgram nova-3 en-US if not provided."
        ),
    )


class CreateVapiAssistantResponse(BaseModel):
    """Response model for creating a VAPI assistant or squad."""

    assistantId: str | None = Field(
        None,
        description="The ID of the created VAPI assistant (only set for single-group requests)",
    )
    squadId: str | None = Field(
        None,
        description="The ID of the created VAPI squad (only set for multi-group requests)",
    )


vapi_router = APIRouter(prefix="/vapi", tags=["Integrations"])


@vapi_router.post(
    "",
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
    status_code=status.HTTP_201_CREATED,
    response_model=CreateVapiAssistantResponse,
    responses={
        201: {
            "model": CreateVapiAssistantResponse,
            "description": "Assistant created successfully",
        },
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_vapi_assistant(
    create_request: CreateVapiAssistantRequest,
) -> CreateVapiAssistantResponse:
    """
    Create a new VAPI assistant or squad.

    This endpoint creates a new assistant or squad with the provided configurable fields:
    - name: Assistant or squad name
    - firstMessage: Optional greeting message
    - maxDurationSeconds: Optional call duration limit
    - systemPrompt: System prompt for the AI model
    - voice: Voice configuration from admin console (provider, model, voiceId)
    - languageGroups: Language groups that define single vs squad creation
    - transcribers: Optional per-group transcriber configs (provider, model, language, etc.)

    Fixed configuration:
    - Model: OpenAI GPT-4o with temperature 0.3
    """
    try:
        result = await handle_create_vapi_assistant(create_request)
        return CreateVapiAssistantResponse(
            assistantId=result["assistantId"],
            squadId=result["squadId"],
        )
    except ValueError as e:
        # Validation or input errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # All other errors
        raise HTTPException(
            status_code=500, detail=f"Failed to create VAPI assistant: {str(e)}"
        )
