import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._utils import UserContext, not_found_error
from api.schemas.admin.phone_number import (
    ListPhoneNumbersResponse,
    PhoneNumberInfo,
    ReleaseProjectNumberRequest,
    ReserveProjectNumberRequest,
)
from services import project_service
from services.number_service import NumberService
from services.project_service import ProjectParams
from utils.log import logger


async def reserve_phone_number(
    project_id: uuid.UUID,
    request: ReserveProjectNumberRequest,
    context: UserContext,
    session: Session,
):
    """
    Create a new phone number, optionally bind to assistant and project.
    """

    project = project_service.get_project(session, project_id)
    if project is None:
        raise not_found_error(f"Project with id {project_id} not found")

    logger.info(
        "Attempting to reserve a new phone number for project",
        extra={
            "project_id": project_id,
        },
    )

    try:
        number_service = NumberService()
        number_response = number_service.setup_number(
            country_code=request.country_code,
            toll_free=request.toll_free,
            merchant_name=project.name,
        )
    except ValueError as err:
        logger.exception("Failed to setup number")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to setup a new number: {err}",
        )

    channels = list(project.channel_identifiers or [])
    for request_channel in request.channels:
        channels.append(f"{request_channel.value}:{number_response.number}")

    logger.info(
        "Updating project with new channel identifiers",
        extra={"channel_identifiers": channels},
    )

    try:
        project_service.update_project(
            session,
            context,
            project_id,
            params=ProjectParams(
                channel_identifiers=channels,
            ),
            auto_commit=True,
        )
    except Exception:
        logger.exception("Failed to update channel identifiers with new voice number")
        number_service.release_number(number_response.number)
        raise HTTPException(
            status_code=400,
            detail="Failed to update project. The purchased number has been released.",
        )
    logger.info(
        "Successfully reserved new phone number for project",
        extra={
            "project_id": project_id,
            "phone_number": number_response.number,
            "channels": request.channels,
        },
    )


async def release_phone_number(
    project_id: uuid.UUID,
    request: ReleaseProjectNumberRequest,
    context: UserContext,
    session: Session,
):
    project = project_service.get_project(session, project_id)
    if project is None:
        raise not_found_error(f"Project with id {project_id} not found")

    numbers = set(
        [
            channel_identifier.split(":")[1]
            for channel_identifier in project.channel_identifiers or []
            if channel_identifier.split(":")[0] in ["sms", "voice"]
        ]
    )
    if request.phone_number not in numbers:
        raise HTTPException(
            status_code=400,
            detail="Requested phone number does not belong to the given project",
        )

    logger.info(
        "Releasing phone number from project.",
        extra={
            "project_id": project_id,
            "phone_number": request.phone_number,
        },
    )

    try:
        number_service = NumberService()
        number_service.release_number(request.phone_number)
    except Exception:
        logger.exception("Failed to release phone number")
        raise HTTPException(
            status_code=500,
            detail="Failed to release phone number. Please try again later.",
        )

    try:
        new_channel_identifiers = []
        for channel_identifier in project.channel_identifiers or []:
            channel = channel_identifier.split(":")[0]
            identifier = channel_identifier.split(":")[1]
            if channel in ["sms", "voice"] and identifier == request.phone_number:
                continue
            new_channel_identifiers.append(channel_identifier)

        project_service.update_project(
            session,
            context,
            project_id,
            params=ProjectParams(
                channel_identifiers=new_channel_identifiers,
            ),
            auto_commit=True,
        )
    except Exception:
        logger.exception("Failed to update project channel identifiers")
        raise HTTPException(
            status_code=500,
            detail="Failed to update project channel identifiers. Please try again later.",
        )
    logger.info("Successfully released phone number from project")


async def list_phone_numbers(
    context: UserContext,
    session: Session,
    page: int = 1,
    page_size: int = 20,
) -> ListPhoneNumbersResponse:
    """
    List purchased phone numbers from Twilio account for the current environment.

    Args:
        context: User context for authentication
        page: Page number for pagination (1-based, default: 1).
        page_size: Number of numbers per page when pagination is used (default: 20)

    Returns:
        ListPhoneNumbersResponse: List of phone numbers with their details

    Raises:
        HTTPException: If retrieval fails
    """
    # 1. Auth check - ensure only admin users can access
    authorize_admin(context)

    try:
        number_service = NumberService()
        phone_numbers_data, has_more = number_service.list_phone_numbers_with_details(
            session=session, page=page, page_size=page_size
        )

        phone_numbers = []
        for data in phone_numbers_data:
            # Use enum values directly from service - no conversion needed!
            phone_number_info = PhoneNumberInfo(
                phone_number=data["phone_number"],
                friendly_name=data["friendly_name"],
                sid=data["sid"],
                status=data["status"],  # Already a VerificationStatus enum or None
                project_ids=data["project_ids"],
                project_names=data["project_names"],
                account_ids=data["account_ids"],
                account_names=data["account_names"],
                usage_type=data["usage_type"],  # Already a UsageType enum
                number_type=data["number_type"],  # Already a NumberType enum
            )
            phone_numbers.append(phone_number_info)

        return ListPhoneNumbersResponse(
            numbers=phone_numbers,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )

    except Exception as e:
        logger.exception("Failed to retrieve phone numbers")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve phone numbers: {str(e)}",
        )
