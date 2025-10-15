import os
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._utils import UserContext
from api.schemas.admin.checkpoint import Checkpoint, ListCheckpointsResponse
from services import account_service, asset_service, checkpoint_service, project_service
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

        # Return the S3 key (file_path) instead of the presigned URL
        # The presigned URL will be generated when needed via map_uri_to_s3_url
        return file_path

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
    name: str,
    description: str | None,
    is_active: bool,
    group: str | None,
    rules: str | None,
    image: UploadFile | None,
    context: UserContext,
    session: Session,
) -> Checkpoint:
    """
    Create a new checkpoint with an optional image upload.
    If image is provided, it will be uploaded to S3 and the URL stored in the checkpoint.

    Args:
        project_id: UUID of the project
        name: Name of the checkpoint
        description: Optional description
        is_active: Whether the checkpoint is active
        group: Optional group name
        rules: Optional JSON array string of rules
        image: Optional image file to upload
        context: User context for authorization
        session: Database session

    Returns:
        Checkpoint object with all details including image URL if uploaded
    """
    import json

    # Validate & authorize checkpoint create request
    project = project_service.get_project(session, project_id)
    if not project:
        raise not_found_error(f"Project {project_id} does not exist.")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise not_found_error(f"Account for project {project_id} does not exist.")

    authorize_user_account(context, account.name)

    # Parse rules from JSON string if provided
    parsed_rules = None
    if rules:
        try:
            parsed_rules = json.loads(rules)
            if not isinstance(parsed_rules, list):
                raise ValueError("Rules must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid rules format: {str(e)}. Expected JSON array.",
            )

    # Create checkpoint in database first (without image)
    checkpoint = db.CheckPoint(
        project_id=project_id,
        name=name,
        description=description,
        image_url=None,
        is_active=is_active,
        group=group,
        rules=parsed_rules,
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


async def list_checkpoints(
    project_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ListCheckpointsResponse:
    """
    List all checkpoints for a project.

    Args:
        project_id: UUID of the project
        context: User context for authorization
        session: Database session

    Returns:
        ListCheckpointsResponse with all checkpoints for the project
    """
    # Validate & authorize
    project = project_service.get_project(session, project_id)
    if not project:
        raise not_found_error(f"Project {project_id} does not exist.")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise not_found_error(f"Account for project {project_id} does not exist.")

    authorize_user_account(context, account.name)

    # Get checkpoints
    checkpoints = checkpoint_service.list_checkpoints(session, project_id)

    return ListCheckpointsResponse(
        checkpoints=[_builder.build_checkpoint(cp) for cp in checkpoints],
        total=len(checkpoints),
    )


async def update_checkpoint(
    checkpoint_id: uuid.UUID,
    name: str | None,
    description: str | None,
    is_active: bool | None,
    group: str | None,
    rules: str | None,
    image: UploadFile | None,
    context: UserContext,
    session: Session,
) -> Checkpoint:
    """
    Update a checkpoint by ID. All fields are optional.
    If a new image is provided, it will replace the old one.

    Args:
        checkpoint_id: UUID of the checkpoint to update
        name: Optional new name
        description: Optional new description
        is_active: Optional new active status
        group: Optional new group
        rules: Optional new rules (JSON array string)
        image: Optional new image file to replace existing one
        context: User context for authorization
        session: Database session

    Returns:
        Updated Checkpoint object

    Raises:
        HTTPException: If checkpoint not found or authorization fails
    """
    import json

    # Get checkpoint first to validate it exists
    checkpoint = checkpoint_service.get_checkpoint(session, checkpoint_id)
    if not checkpoint:
        raise not_found_error(f"Checkpoint {checkpoint_id} does not exist.")

    # Validate & authorize via project
    project = project_service.get_project(session, checkpoint.project_id)
    if not project:
        raise not_found_error(f"Project {checkpoint.project_id} does not exist.")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise not_found_error(
            f"Account for project {checkpoint.project_id} does not exist."
        )

    authorize_user_account(context, account.name)

    # Parse rules from JSON string if provided
    parsed_rules = None
    if rules is not None:
        try:
            parsed_rules = json.loads(rules)
            if not isinstance(parsed_rules, list):
                raise ValueError("Rules must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid rules format: {str(e)}. Expected JSON array.",
            )

    # Build updates dictionary (only include provided fields)
    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if is_active is not None:
        updates["is_active"] = is_active
    if group is not None:
        updates["group"] = group
    if parsed_rules is not None:
        updates["rules"] = parsed_rules

    # Handle image update if provided
    if image:
        # Delete old image from S3 if it exists
        if checkpoint.image_url:
            try:
                deleted_from_s3 = asset_service.delete_asset(checkpoint.image_url)
                if deleted_from_s3:
                    logger.info(
                        f"Deleted old checkpoint image from S3: {checkpoint.image_url}"
                    )
            except Exception as e:
                # Log but don't fail the operation if old image deletion fails
                logger.warning(f"Failed to delete old checkpoint image from S3: {e}")

        # Upload new image
        new_image_url = await _upload_checkpoint_image(
            image, checkpoint.project_id, checkpoint_id, account.id
        )
        updates["image_url"] = new_image_url

    # Update checkpoint in database
    if updates:
        updated_checkpoint = checkpoint_service.update_checkpoint(
            session, checkpoint_id, updates
        )
        if not updated_checkpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update checkpoint {checkpoint_id}",
            )
        return _builder.build_checkpoint(updated_checkpoint)
    else:
        # No updates provided, return current checkpoint
        return _builder.build_checkpoint(checkpoint)


async def delete_checkpoint(
    checkpoint_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> None:
    """
    Delete a checkpoint by ID.

    Args:
        checkpoint_id: UUID of the checkpoint to delete
        context: User context for authorization
        session: Database session

    Raises:
        HTTPException: If checkpoint not found or authorization fails
    """
    # Get checkpoint first to validate it exists and get project_id
    checkpoint = checkpoint_service.get_checkpoint(session, checkpoint_id)
    if not checkpoint:
        raise not_found_error(f"Checkpoint {checkpoint_id} does not exist.")

    # Validate & authorize via project
    project = project_service.get_project(session, checkpoint.project_id)
    if not project:
        raise not_found_error(f"Project {checkpoint.project_id} does not exist.")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise not_found_error(
            f"Account for project {checkpoint.project_id} does not exist."
        )

    authorize_user_account(context, account.name)

    # Delete checkpoint image from S3 if it exists
    if checkpoint.image_url:
        # Try common image extensions
        # Format: checkpoints/{project_id}/{checkpoint_id}{extension}
        common_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        for ext in common_extensions:
            file_path = os.path.join(
                "checkpoints",
                str(checkpoint.project_id),
                f"{checkpoint_id}{ext}",
            )
            try:
                deleted_from_s3 = asset_service.delete_asset(file_path)
                if deleted_from_s3:
                    logger.info(f"Deleted checkpoint image from S3: {file_path}")
                    break  # Stop after finding and deleting the file
            except Exception as e:
                # Log but don't fail the entire operation if S3 deletion fails
                logger.warning(f"Failed to delete checkpoint image from S3: {e}")

    # Delete checkpoint from database
    deleted = checkpoint_service.delete_checkpoint(session, checkpoint_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete checkpoint {checkpoint_id}",
        )
