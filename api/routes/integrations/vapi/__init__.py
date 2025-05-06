from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.endpoints import endpoints
from api.schemas.error.error import ErrorResponse

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
