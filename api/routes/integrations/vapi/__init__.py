from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse

from ._implementation import api_vapi_server, handle_create_vapi_assistant


class CreateVapiAssistantRequest(BaseModel):
    """Request model for creating a VAPI assistant."""

    name: str = Field(..., description="Assistant name")
    firstMessage: str | None = Field(None, description="Optional greeting message")
    maxDurationSeconds: int | None = Field(
        None, description="Optional call duration limit in seconds"
    )
    systemPrompt: str = Field(..., description="System prompt for the AI model")
    voiceId: str = Field(..., description="Voice ID for speech synthesis")
    language: str = Field(
        ...,
        description="Language: English, Spanish, Chinese, or Multilingual (creates a squad with all languages)",
    )


class CreateVapiAssistantResponse(BaseModel):
    """Response model for creating a VAPI assistant or squad."""

    assistantId: str = Field(
        ...,
        description="The ID of the created VAPI assistant (or squad ID if language is Multilingual)",
    )


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
    - voiceId: Voice ID for speech synthesis

    Fixed configuration:
    - Transcriber: Deepgram with en-US language
    - Model: OpenAI GPT-4o with temperature 0.7
    - Voice Provider: Cartesia
    """
    try:
        assistant_id = await handle_create_vapi_assistant(create_request)
        return CreateVapiAssistantResponse(assistantId=assistant_id)
    except ValueError as e:
        # Validation or input errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # All other errors
        raise HTTPException(
            status_code=500, detail=f"Failed to create VAPI assistant: {str(e)}"
        )
