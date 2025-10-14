import os
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._utils import UserContext
from api.schemas.admin.checkpoint import Checkpoint, CreateCheckpointRequest
from services import account_service, checkpoint_service, project_service
from services.asset_service import write_asset
from services.asset_service._implementation import WriteAssetRequest
from utils.log import logger

from . import _builder
from ._auth import authorize_user_account
from ._utils import not_found_error


async def _upload_checkpoint_image(
    image: UploadFile,
    project_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    account_id: uuid.UUID,
) -> str:
    """
    Upload checkpoint image to S3 and return the URL.

    Each checkpoint can only have one image. Uploading a new image will replace
    the existing one (by using the checkpoint_id as the identifier).

    Args:
        image: The uploaded image file
        project_id: Project UUID
        checkpoint_id: Checkpoint UUID (used as identifier)
        account_id: Account UUID

    Returns:
        str: S3 presigned URL of the uploaded image

    Raises:
        HTTPException: If image upload fails
    """
    try:
        logger.info(f"Uploading checkpoint image: {image.filename}")

        if not image.filename:
            raise ValueError("Image filename is required.")

        # Read image content
        content = await image.read()

        # Get file extension
        file_extension = os.path.splitext(image.filename)[1] or ".jpg"

        # Create S3 path using checkpoint_id as identifier
        # Format: checkpoints/{project_id}/{checkpoint_id}{extension}
        # This ensures one image per checkpoint - new uploads replace the old one
        file_path = os.path.join(
            "checkpoints",
            str(project_id),
            f"{checkpoint_id}{file_extension}",
        )

        # Upload to S3 with metadata
        write_asset_req = WriteAssetRequest(
            name=file_path,
            content=content,
            metadata={
                "project_id": str(project_id),
                "checkpoint_id": str(checkpoint_id),
                "account_id": str(account_id),
            },
        )

        asset_response = write_asset(write_asset_req)
        logger.info(f"Checkpoint image uploaded successfully: {asset_response.url}")

        return asset_response.url

    except ValueError as ve:
        logger.error(f"Validation error uploading checkpoint image: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error uploading checkpoint image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload checkpoint image: {str(e)}",
        )


async def create_checkpoint(
    project_id: uuid.UUID,
    checkpoint_request: str | CreateCheckpointRequest,
    image: UploadFile | None,
    context: UserContext,
    session: Session,
) -> Checkpoint:
    """
    Create a new checkpoint with an optional image upload.
    If image is provided, it will be uploaded to S3 and the URL stored in the checkpoint.

    Args:
        project_id: UUID of the project
        checkpoint_request: Either a JSON string or CreateCheckpointRequest object
        image: Optional image file to upload
        session: Database session

    Returns:
        Checkpoint object with all details including image URL if uploaded
    """
    from pydantic import ValidationError

    # Parse JSON string if needed
    if isinstance(checkpoint_request, str):
        try:
            checkpoint_create = CreateCheckpointRequest.model_validate_json(
                checkpoint_request
            )
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid checkpoint_request format: {str(e)}",
            )
    else:
        checkpoint_create = checkpoint_request

    # Validate & authorize checkpoint create request
    project = project_service.get_project(session, project_id)
    if not project:
        raise not_found_error(f"Project {project_id} does not exist.")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise not_found_error(f"Account for project {project_id} does not exist.")

    authorize_user_account(context, account.name)

    # Validate that the project_id in the request matches the path parameter
    if checkpoint_create.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID in request body does not match the path parameter.",
        )

    # Create checkpoint in database first (without image)
    checkpoint = db.CheckPoint(
        project_id=checkpoint_create.project_id,
        name=checkpoint_create.name,
        description=checkpoint_create.description,
        image_url=None,
        is_active=checkpoint_create.is_active,
        group=checkpoint_create.group,
        rules=checkpoint_create.rules,
    )

    persisted_checkpoint = checkpoint_service.create_checkpoint(session, checkpoint)

    # Upload image if provided (using checkpoint_id as identifier)
    if image:
        image_url = await _upload_checkpoint_image(
            image, project_id, persisted_checkpoint.id, account.id
        )

        # Update checkpoint with image URL
        persisted_checkpoint.image_url = image_url
        session.commit()
        session.refresh(persisted_checkpoint)

    return _builder.build_checkpoint(persisted_checkpoint)
