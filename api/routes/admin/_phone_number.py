import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.routes.admin._auth import authorize_admin
from api.routes.admin._utils import not_found_error
from api.schemas.admin.phone_number import (
    EnhancedReleaseProjectNumberRequest,
    EnhancedReleaseProjectNumberResponse,
    ListPhoneNumbersResponse,
    PhoneNumberInfo,
    PurchaseNumberRequest,
    PurchaseNumberResponse,
    ReleaseNumberRequest,
    ReleaseNumberResponse,
    ReleaseProjectNumberRequest,
    ReserveProjectNumberRequest,
)
from services import project_service
from services.auth_types import UserContext
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
    Create a new phone number or reserve an existing one for a project.
    """
    authorize_admin(context)

    project = project_service.get_project(session, project_id)
    if project is None:
        raise not_found_error(f"Project with id {project_id} not found")

    number_service = NumberService()

    # Use the unified service method to handle both existing and new numbers
    try:
        phone_number = number_service.assign_phone_number_to_project(
            project_id=project_id,
            project_name=project.name,
            channels=request.channels,
            session=session,
            context=context,
            phone_number=request.phone_number,  # None for new numbers
            country_code=request.country_code,
            toll_free=request.toll_free,
        )
    except ValueError as err:
        # Determine appropriate HTTP status based on the error
        if request.phone_number:
            # Existing number issues are client errors
            raise HTTPException(
                status_code=400,
                detail=f"Failed to reserve existing number: {err}",
            )
        else:
            # New number purchase issues are server errors
            raise HTTPException(
                status_code=500,
                detail=f"Failed to setup new number: {err}",
            )

    logger.info(
        "Successfully reserved phone number for project",
        extra={
            "project_id": project_id,
            "phone_number": phone_number,
            "channels": request.channels,
            "existing_number": bool(request.phone_number),
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


async def release_phone_number_enhanced(
    project_id: uuid.UUID,
    request: EnhancedReleaseProjectNumberRequest,
    context: UserContext,
    session: Session,
) -> EnhancedReleaseProjectNumberResponse:
    """Enhanced phone number release with options for reuse or permanent deletion."""
    authorize_admin(context)

    # Use the unified service method to handle complete release workflow
    try:
        number_service = NumberService()
        message = number_service.release_phone_number_from_project(
            project_id=project_id,
            phone_number=request.phone_number,
            release_type=request.release_type,
            session=session,
            context=context,
        )

        return EnhancedReleaseProjectNumberResponse(
            phone_number=request.phone_number,
            release_type=request.release_type,
            message=message,
        )

    except ValueError as err:
        # Business logic errors (validation, phone number not found, etc.)
        raise HTTPException(
            status_code=400,
            detail=str(err),
        )
    except Exception as err:
        # Unexpected system errors
        logger.exception(
            "Enhanced release failed",
            extra={
                "project_id": project_id,
                "phone_number": request.phone_number,
                "release_type": request.release_type.value,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to release phone number: {str(err)}",
        )


async def list_phone_numbers(
    context: UserContext,
    session: Session,
    page: int = 1,
    page_size: int = 20,
    friendly_name: str | None = None,
    phone_number: str | None = None,
) -> ListPhoneNumbersResponse:
    """
    List purchased phone numbers using unified streaming pagination approach.

    Three efficient filtering scenarios with consistent streaming implementation:
    1. Phone number: Partial match + environment prefix (hybrid: native+environment check) - HIGHEST PRIORITY
    2. Friendly name: Exact match with native optimization (hybrid approach)
    3. Environment-only: All numbers for current env (pure streaming)

    Args:
        context: User context for authentication
        page: Page number for pagination (1-based, default: 1).
        page_size: Number of numbers per page when pagination is used (default: 20)
        friendly_name: Optional friendly name to filter by (exact match with env prefix)
        phone_number: Optional phone number to filter by (partial match + env requirement)

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
            session=session,
            page=page,
            page_size=page_size,
            friendly_name=friendly_name,
            phone_number=phone_number,
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


async def purchase_number(
    request: PurchaseNumberRequest,
    context: UserContext,
    session: Session,
) -> PurchaseNumberResponse:
    """
    Purchase a single phone number.
    """

    # 1. Auth check - ensure only admin users can access
    authorize_admin(context)

    logger.info(
        "Starting phone number purchase request",
        extra={
            "country_code": request.country_code,
            "toll_free": request.toll_free,
            "area_code": request.area_code,
            "contains": request.contains,
        },
    )

    try:
        number_service = NumberService()
        number_response = number_service.setup_number(
            country_code=request.country_code,
            toll_free=request.toll_free,
            merchant_name="AVAILABLE",  # Purchased numbers use "AVAILABLE" label
            purchase_number=True,  # Force purchase new number
            area_code=request.area_code,
            contains=request.contains,
        )

        logger.info(
            f"Phone number purchased successfully: {number_response.number}",
            extra={
                "phone_number": number_response.number,
                "country_code": request.country_code,
                "toll_free": request.toll_free,
            },
        )

        return PurchaseNumberResponse(
            phone_number=number_response.number,
            merchant_name=number_response.merchant_name,
            country_code=number_response.country_code,
            toll_free=number_response.toll_free,
        )

    except ValueError as e:
        logger.error("Purchase failed with business error", extra={"detail": str(e)})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to purchase phone number")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to purchase phone number: {str(e)}",
        )


async def release_standalone_number(
    request: ReleaseNumberRequest,
    context: UserContext,
    session: Session,
) -> ReleaseNumberResponse:
    """
    Release a standalone phone number (not associated with any project).
    """

    # 1. Auth check - ensure only admin users can access
    authorize_admin(context)

    logger.info(
        f"Starting standalone number release request for {request.phone_number}",
        extra={"phone_number": request.phone_number},
    )

    try:
        number_service = NumberService()

        number_service.delete_number(request.phone_number)

        success_message = f"Number {request.phone_number} deleted successfully from both Vapi and Twilio"
        logger.info(success_message)

        return ReleaseNumberResponse(
            phone_number=request.phone_number,
            message=success_message,
            released_from_vapi=True,  # Assume success if no exception
            released_from_twilio=True,
        )

    except ValueError as e:
        logger.error("Release failed with business error", extra={"detail": str(e)})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to release standalone phone number")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to release phone number: {str(e)}",
        )
