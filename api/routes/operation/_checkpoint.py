import asyncio
import base64
import os
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin import _builder
from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import UserContext, not_found_error
from api.routes.utils import map_uri_to_s3_url
from api.schemas.admin.checkpoint import (
    Checkpoint,
    ListCheckpointResultsByCheckpointResponse,
    ListCheckpointResultsBySubmissionResponse,
    ListCheckpointsResponse,
    RecordCheckpointRunResponse,
)
from db.tables.types import CheckStatus
from services import account_service, asset_service, checkpoint_service, project_service
from services.asset_service import write_asset
from services.asset_service._implementation import WriteAssetRequest
from utils.log import logger


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


async def _upload_checkpoint_run_image(
    image: UploadFile,
    project_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    run_id: uuid.UUID,
    account_id: uuid.UUID,
) -> str:
    """
    Upload checkpoint run image to S3 and return the URL.

    Args:
        image: The uploaded image file
        project_id: Project UUID
        checkpoint_id: Checkpoint UUID
        run_id: Checkpoint run UUID
        account_id: Account UUID

    Returns:
        str: S3 file path (key)

    Raises:
        HTTPException: If image upload fails
    """
    try:
        logger.info(f"Uploading checkpoint run image: {image.filename}")

        if not image.filename:
            raise ValueError("Image filename is required.")

        # Read image content
        content = await image.read()

        # Get file extension
        file_extension = os.path.splitext(image.filename)[1] or ".jpg"

        # Create S3 path
        # Format: checkpoint_runs/{project_id}/{checkpoint_id}/{run_id}{extension}
        file_path = os.path.join(
            "checkpoint_runs",
            str(project_id),
            str(checkpoint_id),
            f"{run_id}{file_extension}",
        )

        # Upload to S3 with metadata
        write_asset_req = WriteAssetRequest(
            name=file_path,
            content=content,
            metadata={
                "project_id": str(project_id),
                "checkpoint_id": str(checkpoint_id),
                "run_id": str(run_id),
                "account_id": str(account_id),
            },
        )

        asset_response = write_asset(write_asset_req)
        logger.info(f"Checkpoint run image uploaded successfully: {asset_response.url}")

        # Return the S3 key (file_path)
        return file_path

    except ValueError as ve:
        logger.error(f"Validation error uploading checkpoint run image: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Error uploading checkpoint run image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload checkpoint run image: {str(e)}",
        )


async def create_checkpoint(
    project_id: uuid.UUID,
    checklist_id: uuid.UUID | None,
    name: str,
    description: str | None,
    is_active: bool,
    group: str | None,
    rules: str | None,
    requires_image: bool,
    image: UploadFile | None,
    context: UserContext,
    session: Session,
) -> Checkpoint:
    """
    Create a new checkpoint with an optional image upload.
    If image is provided, it will be uploaded to S3 and the URL stored in the checkpoint.

    Args:
        project_id: UUID of the project
        checklist_id: Optional UUID of the checklist this checkpoint belongs to
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
        checklist_id=checklist_id,
        name=name,
        description=description,
        image_url=None,
        is_active=is_active,
        group=group,
        rules=parsed_rules,
        requires_image=requires_image,
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


async def list_checkpoints_by_checklist(
    checklist_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ListCheckpointsResponse:
    """
    List all checkpoints for a checklist.

    Args:
        checklist_id: UUID of the checklist
        context: User context for authorization
        session: Database session

    Returns:
        ListCheckpointsResponse with all checkpoints for the checklist
    """
    # Get the checklist first to verify it exists and get its project_id
    from db.repositories import checklist_repository

    checklist = checklist_repository.get_checklist_by_id(session, checklist_id)
    if not checklist:
        raise not_found_error(f"Checklist {checklist_id} does not exist.")

    # Validate & authorize via project
    if checklist.project_id:
        project = project_service.get_project(session, checklist.project_id)
        if not project:
            raise not_found_error(f"Project {checklist.project_id} does not exist.")

        account = account_service.get_account_by_id(session, project.account_id)
        if not account:
            raise not_found_error(
                f"Account for project {checklist.project_id} does not exist."
            )

        authorize_user_account(context, account.name)

    # Get checkpoints for this checklist
    checkpoints = checkpoint_service.list_checkpoints_by_checklist(
        session, checklist_id
    )

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
    requires_image: bool | None,
    checklist_id: uuid.UUID | None,
    unassign_checklist: bool,
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
        checklist_id: Optional checklist_id to assign
        unassign_checklist: If True, sets checklist_id to None (takes precedence over checklist_id)
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
    if requires_image is not None:
        updates["requires_image"] = requires_image

    # Handle checklist_id assignment/unassignment
    # unassign_checklist takes precedence over checklist_id
    if unassign_checklist:
        updates["checklist_id"] = None
    elif checklist_id is not None:
        updates["checklist_id"] = checklist_id

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


async def compare_checkpoint(
    checkpoint_id: uuid.UUID,
    image: UploadFile,
    context: UserContext,
    session: Session,
    submission_id: str | None = None,
) -> dict:
    """
    Compare an uploaded image with a checkpoint's image.

    This endpoint takes an uploaded image and compares it with the checkpoint's stored image
    using OpenAI's Vision API to determine if they match according to the checkpoint's
    description and rules.

    Args:
        checkpoint_id: UUID of the checkpoint to compare against
        image: The uploaded image file to compare
        context: User context for authorization
        session: Database session
        submission_id: Optional submission ID from frontend (UUID string)

    Returns:
        dict: Comparison result with match status and explanation
    """
    # Get checkpoint and validate it exists
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

    # Check if checkpoint has an image
    if not checkpoint.image_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Checkpoint {checkpoint_id} does not have an image to compare against.",
        )

    try:
        # Read and encode the uploaded image
        uploaded_image_content = await image.read()
        uploaded_image_base64 = base64.b64encode(uploaded_image_content).decode("utf-8")

        # Step 1: Parse or generate submission_id
        if submission_id:
            try:
                submission_uuid = uuid.UUID(submission_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid submission_id format: {submission_id}. Must be a valid UUID.",
                )
        else:
            # Auto-generate if not provided
            submission_uuid = uuid.uuid4()

        # Step 2: Create checkpoint_result with 'processing' status immediately
        checkpoint_result = checkpoint_service.create_checkpoint_result_processing(
            session=session,
            checkpoint_id=checkpoint_id,
            submission_id=submission_uuid,
        )

        # Step 3: Start background task to run OpenAI comparison
        asyncio.create_task(
            checkpoint_service.compare_and_update_checkpoint_background(
                checkpoint_result_id=checkpoint_result.id,
                checkpoint=checkpoint,
                uploaded_image_base64=uploaded_image_base64,
            )
        )

        # Step 4: Return 200 immediately with processing status
        return {
            "checkpoint_result_id": str(checkpoint_result.id),
            "checkpoint_id": str(checkpoint_id),
            "checkpoint_name": checkpoint.name,
            "checkpoint_description": checkpoint.description,
            "checkpoint_rules": checkpoint.rules,
            "submission_id": str(submission_uuid),
            "status": "processing",
            "message": "Comparison started. Check result status using checkpoint_result_id.",
            "created_at": checkpoint_result.created_at.isoformat(),
        }

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        logger.error(f"Error starting checkpoint comparison: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start comparison: {str(e)}",
        )


async def list_checkpoint_results_by_submission(
    status_filter: CheckStatus | None,
    project_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ListCheckpointResultsBySubmissionResponse:
    """
    List all checkpoint results grouped by submission_id for a specific project.

    This endpoint returns checkpoint results filtered by the required project_id,
    with authorization enforced to ensure user has access to that project.
    Results now include review information (review, reviewer, is_reviewed).

    Args:
        status_filter: Optional filter by status (processing, active, failed)
        project_id: Required project ID to filter checkpoint results
        context: User context for authorization
        session: Database session

    Returns:
        ListCheckpointResultsBySubmissionResponse with results grouped by submission_id,
        each result includes review fields (review, reviewer, is_reviewed)

    Raises:
        HTTPException: If project not found or authorization fails
    """
    # Validate & authorize project access
    project = project_service.get_project(session, project_id)
    if not project:
        raise not_found_error(f"Project {project_id} does not exist.")

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise not_found_error(f"Account for project {project_id} does not exist.")

    authorize_user_account(context, account.name)

    # Get all checkpoint results with status and project filters
    checkpoint_results = checkpoint_service.list_checkpoint_results(
        session=session,
        checkpoint_id=None,
        submission_id=None,
        status=status_filter,
        project_id=project_id,
    )

    # Group results by submission_id
    grouped_results: dict[str, list] = {}
    for result in checkpoint_results:
        submission_id_str = str(result.submission_id)
        if submission_id_str not in grouped_results:
            grouped_results[submission_id_str] = []
        grouped_results[submission_id_str].append(
            _builder.build_checkpoint_result(result)
        )

    return ListCheckpointResultsBySubmissionResponse(
        results=grouped_results,
        total_submissions=len(grouped_results),
    )


async def list_checkpoint_results_by_checkpoint(
    checkpoint_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ListCheckpointResultsByCheckpointResponse:
    """
    List all checkpoint results for a specific checkpoint.

    Args:
        checkpoint_id: UUID of the checkpoint
        context: User context for authorization
        session: Database session

    Returns:
        ListCheckpointResultsByCheckpointResponse with all results for the checkpoint

    Raises:
        HTTPException: If checkpoint not found or authorization fails
    """
    # Get checkpoint and validate it exists
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

    # Get all checkpoint results for this checkpoint
    checkpoint_results = checkpoint_service.list_checkpoint_results(
        session=session,
        checkpoint_id=checkpoint_id,
        submission_id=None,
        status=None,
    )

    return ListCheckpointResultsByCheckpointResponse(
        results=[
            _builder.build_checkpoint_result(result) for result in checkpoint_results
        ],
        total=len(checkpoint_results),
    )


async def record_checkpoint_run(
    checkpoint_id: uuid.UUID,
    status_param: str,
    image: UploadFile | None,
    context: UserContext,
    session: Session,
) -> RecordCheckpointRunResponse:
    """
    Record a checkpoint run with a simple status and optional image.

    Creates a new run record for the checkpoint with status "done" or "missing".

    Args:
        checkpoint_id: UUID of the checkpoint
        status_param: "done" or "missing"
        image: Optional image file
        context: User authentication context
        session: Database session

    Returns:
        RecordCheckpointRunResponse with run details

    Raises:
        HTTPException: If checkpoint not found, unauthorized, or invalid status
    """
    # Validate status
    if status_param not in ["done", "missing"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {status_param}. Must be 'done' or 'missing'",
        )

    # Get checkpoint
    checkpoint = checkpoint_service.get_checkpoint(session, checkpoint_id)
    if not checkpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint {checkpoint_id} not found",
        )

    # Get project and authorize
    project = project_service.get_project(session, checkpoint.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {checkpoint.project_id} not found",
        )

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {project.account_id} not found",
        )

    authorize_user_account(context, account.name)

    # Record the run first to get the run_id (creates exactly ONE run)
    try:
        run = checkpoint_service.record_checkpoint_run(
            session=session,
            checkpoint_id=checkpoint_id,
            status_value=status_param,
            image_url=None,  # No image URL yet
        )

        image_url = None
        # Upload image if provided and update the existing run
        if image:
            image_url = await _upload_checkpoint_run_image(
                image=image,
                project_id=checkpoint.project_id,
                checkpoint_id=checkpoint_id,
                run_id=run.id,  # Use the run_id from the created run
                account_id=project.account_id,
            )

            # Update the EXISTING run with image URL (does NOT create a new run)
            run = checkpoint_service.update_checkpoint_run_image(
                session=session,
                run_id=run.id,
                image_url=image_url,
            )

        # Convert S3 file path to presigned URL if image was uploaded
        presigned_url = map_uri_to_s3_url(image_url) if image_url else None

        return RecordCheckpointRunResponse(
            run_id=str(run.id),
            checkpoint_id=str(run.checkpoint_id),
            status=status_param,
            image_url=presigned_url,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


async def update_checkpoint_run_review_fields(
    run_id: uuid.UUID,
    review: str | None,
    reviewer: str | None,
    is_reviewed: bool | None,
    context: UserContext,
    session: Session,
) -> dict:
    """
    Update review fields (review, reviewer, is_reviewed) for a checkpoint run.

    Args:
        run_id: UUID of the checkpoint run to update
        review: Optional review comments/notes
        reviewer: Optional reviewer name or email
        is_reviewed: Optional reviewed status flag
        context: User context for authorization
        session: Database session

    Returns:
        dict: Success message with updated run details

    Raises:
        HTTPException: If run not found or authorization fails
    """
    # Get the checkpoint run to validate it exists and get its checkpoint
    run = checkpoint_service.get_checkpoint_result(session, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint run {run_id} not found",
        )

    # Get checkpoint to validate authorization
    checkpoint = checkpoint_service.get_checkpoint(session, run.checkpoint_id)
    if not checkpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint {run.checkpoint_id} not found",
        )

    # Validate & authorize via project
    project = project_service.get_project(session, checkpoint.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {checkpoint.project_id} not found",
        )

    account = account_service.get_account_by_id(session, project.account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {project.account_id} not found",
        )

    authorize_user_account(context, account.name)

    # Update the review fields
    try:
        updated_run = checkpoint_service.update_checkpoint_run_review(
            session=session,
            run_id=run_id,
            review=review,
            reviewer=reviewer,
            is_reviewed=is_reviewed,
        )

        return {
            "message": "Review fields updated successfully",
            "run_id": str(updated_run.id),
            "review": updated_run.review,
            "reviewer": updated_run.reviewer,
            "is_reviewed": updated_run.is_reviewed,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
