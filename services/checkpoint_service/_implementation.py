import asyncio
import base64
import json
import os
from datetime import datetime
from uuid import UUID

import boto3
import openai
from sqlalchemy.orm import Session

import db
from db.repositories import checkpoint_repository
from db.tables.types import CheckStatus
from services.asset_service._constants import AWS_ASSET_BUCKET_NAME, AWS_REGION
from utils.log import logger

from . import _constants


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    return checkpoint_repository.create_checkpoint(session, checkpoint)


def list_checkpoints(session: Session, project_id: UUID) -> list[db.CheckPoint]:
    return checkpoint_repository.list_checkpoints(session, project_id)


def list_checkpoints_by_checklist(
    session: Session, checklist_id: UUID
) -> list[db.CheckPoint]:
    return checkpoint_repository.list_checkpoints_by_checklist(session, checklist_id)


def get_checkpoint(session: Session, checkpoint_id: UUID) -> db.CheckPoint | None:
    return checkpoint_repository.get_checkpoint(session, checkpoint_id)


def update_checkpoint(
    session: Session, checkpoint_id: UUID, updates: dict
) -> db.CheckPoint | None:
    return checkpoint_repository.update_checkpoint(session, checkpoint_id, updates)


def delete_checkpoint(session: Session, checkpoint_id: UUID) -> bool:
    return checkpoint_repository.delete_checkpoint(session, checkpoint_id)


async def compare_checkpoint_images_async(
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> dict:
    """
    Async version: Compare an uploaded image with a checkpoint's reference image using OpenAI Vision API.

    Args:
        checkpoint: The checkpoint database object with image_url and rules
        uploaded_image_base64: Base64 encoded string of the uploaded image

    Returns:
        Dictionary containing comparison results with structured JSON

    Raises:
        Exception: If S3 retrieval or OpenAI API call fails
    """
    # Run the blocking comparison in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, compare_checkpoint_images, checkpoint, uploaded_image_base64
    )


def compare_checkpoint_images(
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> dict:
    """
    Compare an uploaded image with a checkpoint's reference image using OpenAI Vision API.

    Args:
        checkpoint: The checkpoint database object with image_url and rules
        uploaded_image_base64: Base64 encoded string of the uploaded image

    Returns:
        Dictionary containing comparison results with structured JSON

    Raises:
        Exception: If S3 retrieval or OpenAI API call fails
    """
    # Get the checkpoint's image from S3
    s3_client = (
        boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("LOCAL_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("LOCAL_AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("LOCAL_AWS_SESSION_TOKEN"),
        )
        if os.getenv("LOCAL_AWS_ACCESS_KEY_ID")
        else boto3.client("s3", region_name=AWS_REGION)
    )

    try:
        s3_response = s3_client.get_object(
            Bucket=AWS_ASSET_BUCKET_NAME, Key=checkpoint.image_url
        )
        checkpoint_image_content = s3_response["Body"].read()
    except Exception as e:
        logger.error(f"Failed to retrieve checkpoint image from S3: {e}")
        raise Exception("Failed to retrieve checkpoint image from storage.")

    checkpoint_image_base64 = base64.b64encode(checkpoint_image_content).decode("utf-8")

    # Build the comparison prompt - check if this is a camera checkpoint
    checkpoint_rules = checkpoint.rules if checkpoint.rules else []
    rules_count = len(checkpoint_rules)

    # Use camera monitoring prompt only if group is "camera"
    checkpoint_group = (checkpoint.group or "").lower()
    is_camera_checkpoint = checkpoint_group == "camera"

    if is_camera_checkpoint:
        # Camera monitoring: minimal prompt, user provides full instructions in rules
        rules_section = "\n".join(checkpoint_rules) if checkpoint_rules else ""
        prompt = _constants.CAMERA_MONITORING_SYSTEM_MESSAGE.format(
            checkpoint_name=checkpoint.name,
            checkpoint_description=checkpoint.description or "N/A",
            rules_section=rules_section,
        )
        logger.info(f"Using camera monitoring prompt for checkpoint {checkpoint.name}")
    else:
        # Manual checkpoint: structured prompt with PASS/FAIL format
        rules_section = ""
        rules_example = ""

        if checkpoint_rules:
            rules_text = "\n".join(
                f"{i+1}. {rule}" for i, rule in enumerate(checkpoint_rules)
            )
            rules_section = _constants.RULES_SECTION_TEMPLATE.format(
                rules_count=rules_count,
                rules_text=rules_text,
            )
            rules_example = _constants.RULES_EXAMPLE_TEMPLATE.format(
                rules_count=rules_count
            )

        prompt = _constants.CHECKPOINT_COMPARISON_SYSTEM_MESSAGE.format(
            checkpoint_name=checkpoint.name,
            checkpoint_description=checkpoint.description or "N/A",
            rules_section=rules_section,
            rules_example=rules_example,
            rules_count=rules_count,
        )
        logger.info(f"Using manual inspection prompt for checkpoint {checkpoint.name}")

    # Call OpenAI Vision API with JSON response format
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=_constants.OPENAI_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{checkpoint_image_base64}",
                            "detail": _constants.OPENAI_IMAGE_DETAIL,
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{uploaded_image_base64}",
                            "detail": _constants.OPENAI_IMAGE_DETAIL,
                        },
                    },
                ],
            }
        ],
        response_format=_constants.OPENAI_RESPONSE_FORMAT,  # type: ignore[arg-type]
        max_tokens=_constants.OPENAI_MAX_TOKENS,
    )

    comparison_result_json = json.loads(response.choices[0].message.content or "{}")

    logger.info(
        f"Checkpoint comparison completed for checkpoint {checkpoint.id}. "
        f"Result: {comparison_result_json.get('overall_result', 'UNKNOWN')}, "
        f"Confidence: {comparison_result_json.get('confidence_score', 0)}%"
    )

    return comparison_result_json


def create_checkpoint_result_processing(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
) -> db.CheckpointRun:
    """
    Create a checkpoint result with 'processing' status immediately.
    This is called BEFORE OpenAI starts processing.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked

    Returns:
        db.CheckpointRun: The created checkpoint result record with processing status
    """
    return checkpoint_repository.create_checkpoint_result_processing(
        session, checkpoint_id, submission_id
    )


def list_checkpoint_results(
    session: Session,
    checkpoint_id: UUID | None = None,
    submission_id: UUID | None = None,
    status: CheckStatus | None = None,
    project_id: UUID | None = None,
) -> list[db.CheckpointRun]:
    """
    List checkpoint results with optional filters.

    Args:
        session: Database session
        checkpoint_id: Optional filter by checkpoint ID
        submission_id: Optional filter by submission ID
        status: Optional filter by status
        project_id: Optional filter by project ID (via checkpoint)

    Returns:
        list[db.CheckpointRun]: List of checkpoint results
    """
    return checkpoint_repository.list_checkpoint_results(
        session, checkpoint_id, submission_id, status, project_id
    )


def get_latest_checkpoint_result_by_date_range(
    session: Session,
    checkpoint_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> db.CheckpointRun | None:
    """
    Get the latest checkpoint result for a specific checkpoint, filtered by date range.
    Returns only the most recent result (by created_at) within the date range.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        start_date: Optional start date filter (datetime object)
        end_date: Optional end date filter (datetime object)

    Returns:
        db.CheckpointRun | None: The latest checkpoint result or None if not found
    """
    # Get checkpoint results filtered by date range
    checkpoint_results = checkpoint_repository.list_checkpoint_results(
        session=session,
        checkpoint_id=checkpoint_id,
        submission_id=None,
        status=None,
        start_date=start_date,
        end_date=end_date,
    )

    # Return only the latest result (first one since results are ordered by created_at DESC)
    return checkpoint_results[0] if checkpoint_results else None


def get_checkpoint_result(
    session: Session,
    result_id: UUID,
) -> db.CheckpointRun | None:
    """
    Get a single checkpoint result by ID.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result

    Returns:
        db.CheckpointRun | None: The checkpoint result or None if not found
    """
    return checkpoint_repository.get_checkpoint_result(session, result_id)


def update_checkpoint_result(
    session: Session,
    result_id: UUID,
    result: dict,
    status: CheckStatus,
) -> db.CheckpointRun:
    """
    Update a checkpoint result with the final comparison result.
    This is called AFTER OpenAI finishes processing.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result to update
        result: Dictionary containing the comparison result (JSON)
        status: Final status (active or failed)

    Returns:
        db.CheckpointRun: The updated checkpoint result record
    """
    return checkpoint_repository.update_checkpoint_result(
        session, result_id, result, status
    )


def save_checkpoint_result(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
    result: dict,
    status: CheckStatus = CheckStatus.active,
) -> db.CheckpointRun:
    """
    Save a checkpoint comparison result to the database.
    (Legacy function - prefer using create + update pattern)

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked
        result: Dictionary containing the comparison result (JSON)
        status: Status of the check (default: active)

    Returns:
        db.CheckpointRun: The created checkpoint result record
    """
    return checkpoint_repository.save_checkpoint_result(
        session, checkpoint_id, submission_id, result, status
    )


async def compare_and_save_checkpoint_async(
    session: Session,
    checkpoint: db.CheckPoint,
    submission_id: UUID,
    uploaded_image_base64: str,
) -> db.CheckpointRun:
    """
    Async function to compare checkpoint images and save the result.

    LEGACY VERSION: Creates and saves result after comparison completes.
    For immediate response, use compare_and_update_checkpoint_background() instead.

    Args:
        session: Database session
        checkpoint: The checkpoint to compare against
        submission_id: UUID of the submission being checked
        uploaded_image_base64: Base64 encoded uploaded image

    Returns:
        db.CheckpointRun: The saved checkpoint result
    """
    try:
        # Run comparison asynchronously
        comparison_result = await compare_checkpoint_images_async(
            checkpoint=checkpoint,
            uploaded_image_base64=uploaded_image_base64,
        )

        # Save to database
        checkpoint_result = save_checkpoint_result(
            session=session,
            checkpoint_id=checkpoint.id,
            submission_id=submission_id,
            result=comparison_result,
            status=CheckStatus.active,
        )

        return checkpoint_result

    except Exception as e:
        logger.error(
            f"Error comparing and saving checkpoint {checkpoint.id}: {e}",
            exc_info=True,
        )

        # Save failed result
        error_result = {
            "overall_result": "FAIL",
            "error": str(e),
            "confidence_score": 0,
        }

        checkpoint_result = save_checkpoint_result(
            session=session,
            checkpoint_id=checkpoint.id,
            submission_id=submission_id,
            result=error_result,
            status=CheckStatus.failed,
        )

        return checkpoint_result


async def compare_and_update_checkpoint_background(
    checkpoint_result_id: UUID,
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> None:
    """
    Background task: Compare images and update existing checkpoint result.

    This function is meant to run in the background AFTER returning response to frontend.
    It updates the checkpoint_result from 'processing' to 'active' or 'failed'.

    This function creates a new short-lived Session using SyncSessionLocal to avoid
    reusing the request-scoped Session which may have been closed.

    Args:
        checkpoint_result_id: UUID of the checkpoint result to update
        checkpoint: The checkpoint to compare against
        uploaded_image_base64: Base64 encoded uploaded image

    Returns:
        None (updates database directly)
    """

    def _update_result_sync(
        result_id: UUID,
        result: dict,
        status: CheckStatus,
    ) -> None:
        """
        Synchronous helper to update checkpoint result with proper session management.

        Args:
            result_id: UUID of the checkpoint result to update
            result: Dictionary containing the comparison result (JSON)
            status: Final status (active or failed)
        """
        # Import SyncSessionLocal from db.session
        from db.session import SyncSessionLocal

        # Create a new short-lived Session
        session = SyncSessionLocal()

        try:
            # Update database with result
            update_checkpoint_result(
                session=session,
                result_id=result_id,
                result=result,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error updating checkpoint result {result_id}: {e}")
            raise
        finally:
            # Always close the session
            session.close()

    try:
        logger.info(
            f"Starting background comparison for checkpoint {checkpoint.id}, "
            f"result_id {checkpoint_result_id}"
        )

        # Run comparison asynchronously (this uses run_in_executor internally)
        comparison_result = await compare_checkpoint_images_async(
            checkpoint=checkpoint,
            uploaded_image_base64=uploaded_image_base64,
        )

        # Run the synchronous DB update in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _update_result_sync,
            checkpoint_result_id,
            comparison_result,
            CheckStatus.active,
        )

        logger.info(
            f"Background comparison completed for result_id {checkpoint_result_id}, "
            f"overall_result: {comparison_result.get('overall_result', 'N/A')}"
        )

    except Exception as e:
        logger.error(
            f"Error in background comparison for checkpoint {checkpoint.id}: {e}",
            exc_info=True,
        )

        # Update with failed status
        error_result = {
            "overall_result": "FAIL",
            "error": str(e),
            "confidence_score": 0,
        }

        try:
            # Run the synchronous DB update in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                _update_result_sync,
                checkpoint_result_id,
                error_result,
                CheckStatus.failed,
            )
        except Exception as db_error:
            logger.error(
                f"Failed to save error result for checkpoint_result {checkpoint_result_id}: {db_error}",
                exc_info=True,
            )


def record_checkpoint_run(
    session: Session,
    checkpoint_id: UUID,
    status_value: str,
    image_url: str | None = None,
) -> db.CheckpointRun:
    """
    Record a checkpoint run with a simple status and optional image.

    Creates a new checkpoint run record with the given status.
    Status can be "done" or "missing".

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        status_value: "done" or "missing"
        image_url: Optional S3 file path for the uploaded image

    Returns:
        db.CheckpointRun: The created run record

    Raises:
        ValueError: If checkpoint not found or status invalid
    """
    # Verify checkpoint exists
    checkpoint = checkpoint_repository.get_checkpoint(session, checkpoint_id)
    if not checkpoint:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    # Validate status
    if status_value not in ["done", "missing"]:
        raise ValueError(f"Invalid status: {status_value}. Must be 'done' or 'missing'")

    # Map status to CheckStatus enum
    if status_value == "done":
        check_status = CheckStatus.active
        result_data = {"status": "done", "recorded_at": datetime.utcnow().isoformat()}
    else:  # missing
        check_status = CheckStatus.failed
        result_data = {
            "status": "missing",
            "recorded_at": datetime.utcnow().isoformat(),
        }

    # Add image URL to result if provided
    if image_url:
        result_data["image_url"] = image_url

    # Create run with a generated submission_id
    import uuid

    submission_id = uuid.uuid4()

    run = checkpoint_repository.save_checkpoint_result(
        session=session,
        checkpoint_id=checkpoint_id,
        submission_id=submission_id,
        result=result_data,
        status=check_status,
    )

    return run


def update_checkpoint_run_image(
    session: Session,
    run_id: UUID,
    image_url: str,
) -> db.CheckpointRun:
    """
    Update an existing checkpoint run with an image URL.

    Args:
        session: Database session
        run_id: UUID of the checkpoint run to update
        image_url: S3 file path for the image

    Returns:
        db.CheckpointRun: The updated run record

    Raises:
        ValueError: If run not found
    """
    # Get the existing run
    run = checkpoint_repository.get_checkpoint_result(session, run_id)
    if not run:
        raise ValueError(f"Checkpoint run {run_id} not found")

    # Update the result with image URL
    result_data = run.result or {}
    result_data["image_url"] = image_url

    # Update the run
    updated_run = checkpoint_repository.update_checkpoint_result(
        session=session,
        result_id=run_id,
        result=result_data,
        status=run.status,
    )

    return updated_run


def compare_camera_images_with_checkpoint(
    session: Session,
    checkpoint: db.CheckPoint,
    start_time: datetime,
    end_time: datetime,
) -> dict:
    """
    Retrieve S3 images for a checkpoint, create processing runs, and start background comparison.

    Args:
        session: Database session
        checkpoint: CheckPoint object (already fetched by handler)
        start_time: Start of time range
        end_time: End of time range

    Returns:
        dict with checkpoint_run_ids, submission_id, checkpoint_id, images_to_compare, status

    Raises:
        ValueError: If invalid parameters
    """
    from uuid import uuid4

    from services import vision_service

    # Extract needed values from checkpoint
    project_id = checkpoint.project_id
    camera_name = checkpoint.name

    logger.info(
        f"Found checkpoint {checkpoint.id} for camera {camera_name}, "
        f"fetching images from {start_time} to {end_time}"
    )

    # Get all S3 image URLs within time range
    image_response = vision_service.get_images_by_time_interval(
        session=session,
        project_id=str(project_id),
        camera_name=camera_name,
        start_time=start_time,
        end_time=end_time,
        limit=None,
    )

    image_urls = image_response.urls

    if not image_urls:
        logger.warning(f"No images found for camera {camera_name} in time range")
        return {
            "checkpoint_run_ids": [],
            "submission_id": None,
            "checkpoint_id": str(checkpoint.id),
            "images_to_compare": 0,
            "status": "completed",
        }

    # Generate single submission_id for the batch
    submission_id = uuid4()

    logger.info(
        f"Creating {len(image_urls)} checkpoint runs with submission_id {submission_id}"
    )

    # Bulk create checkpoint runs with status="processing"
    run_dicts = []
    for url in image_urls:
        # Extract timestamp from URL filename (format: YYYYMMDD_HHMMSS.png)
        timestamp_iso = ""
        s3_key = ""
        try:
            filename = url.split("/")[-1].split("?")[0]
            timestamp_str = filename.rsplit(".", 1)[0]
            image_timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            timestamp_iso = image_timestamp.isoformat()

            # Extract S3 key from presigned URLg
            s3_key = url.split(".amazonaws.com/")[1].split("?")[0]
        except (ValueError, IndexError):
            pass

        run_dicts.append(
            {
                "id": uuid4(),
                "checkpoint_id": checkpoint.id,
                "submission_id": submission_id,
                "status": CheckStatus.processing.value,
                "result": {
                    "image_url": s3_key,
                    "timestamp": timestamp_iso,
                },
            }
        )

    # Use bulk insert for performance
    session.bulk_insert_mappings(db.CheckpointRun, run_dicts)  # type: ignore[arg-type]

    # Extract run IDs
    run_ids = [run_dict["id"] for run_dict in run_dicts]

    logger.info(f"Creating {len(run_ids)} checkpoint runs, starting background task")

    # Start background task to process comparisons
    # Note: Task created BEFORE commit to ensure atomicity
    # If task creation fails, transaction will rollback automatically
    asyncio.create_task(
        _compare_and_update_camera_runs_background(
            checkpoint=checkpoint,
            image_urls=image_urls,
            run_ids=run_ids,
        )
    )

    # Commit only after task creation succeeds
    # This prevents orphaned "processing" records if task creation fails
    # Note: Task is protected by event loop until completion (no manual storage needed)
    session.commit()
    return {
        "checkpoint_run_ids": [str(run_id) for run_id in run_ids],
        "submission_id": str(submission_id),
        "checkpoint_id": str(checkpoint.id),
        "images_to_compare": len(image_urls),
        "status": "processing",
    }


def _download_image_from_url(url: str) -> str:
    """
    Download image from S3 presigned URL and convert to base64.

    Args:
        url: S3 presigned URL (valid for 1 hour)

    Returns:
        Base64-encoded image string suitable for OpenAI Vision API

    Raises:
        requests.HTTPError: If download fails (e.g., 403 Forbidden, 404 Not Found)
        requests.Timeout: If download exceeds timeout (10s connect, 30s read)
    """
    import requests

    try:
        # Connection timeout: 10s, Read timeout: 30s
        response = requests.get(url, timeout=(10, 30))
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to download image from {url[:100]}: {e}")
        raise


def _update_checkpoint_result_sync(
    result_id: UUID,
    result: dict,
    status: CheckStatus,
) -> None:
    """
    Update checkpoint result with proper session management.

    Creates a new database session, updates the result, and commits.
    Rolls back on error and always closes session.

    Args:
        result_id: UUID of the checkpoint run to update
        result: OpenAI comparison result or error details
        status: New status (active for success, failed for error)

    Raises:
        Exception: Re-raises any database errors after rollback
    """
    from db.session import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        update_checkpoint_result(
            session=session,
            result_id=result_id,
            result=result,
            status=status,
        )
    except Exception as e:
        logger.error(f"Failed to update checkpoint result {result_id}: {e}")
        session.rollback()
        raise  # Re-raise to let caller handle database errors
    finally:
        session.close()


async def _process_single_camera_image(
    checkpoint: db.CheckPoint,
    url: str,
    run_id: UUID,
    image_idx: int,
    total_images: int,
) -> None:
    """
    Process a single camera image: download, compare with OpenAI, and save result.

    This function handles the complete lifecycle for one image:
    1. Download from S3 and convert to base64
    2. Send to OpenAI Vision API for comparison
    3. Update database with result (success or error)

    Errors are caught and saved to the database as failed runs, so one
    image failure doesn't affect other images in the batch.

    Args:
        checkpoint: The checkpoint containing reference image and rules
        url: S3 presigned URL for the camera image to analyze
        run_id: UUID of the checkpoint run to update
        image_idx: Image number (1-based, for logging)
        total_images: Total number of images being processed

    Returns:
        None (updates database directly)
    """
    _URL_LOG_LENGTH = 50  # Truncate URLs in logs for readability

    try:
        logger.info(
            f"Processing image {image_idx}/{total_images}: {url[:_URL_LOG_LENGTH]}..."
        )

        # Download image from presigned S3 URL and convert to base64 for OpenAI Vision API
        uploaded_image_base64 = await asyncio.get_event_loop().run_in_executor(
            None, _download_image_from_url, url
        )

        # Send both checkpoint reference image and camera image to OpenAI for comparison
        comparison_result = await compare_checkpoint_images_async(
            checkpoint=checkpoint,
            uploaded_image_base64=uploaded_image_base64,
        )

        # Mark run as 'active' (completed successfully) and store OpenAI analysis result
        _update_checkpoint_result_sync(
            result_id=run_id,
            result=comparison_result,
            status=CheckStatus.active,
        )

        logger.info(
            f"Completed image {image_idx}/{total_images}, "
            f"result: {comparison_result.get('overall_result', 'N/A')}"
        )

    except Exception as e:
        logger.error(
            f"Failed to process image {image_idx}/{total_images} "
            f"({url[:_URL_LOG_LENGTH]}): {e}",
            exc_info=True,
        )

        # Save error details to database so user can see what went wrong for this specific image
        # Other images in the batch will continue processing normally
        error_result = {
            "overall_result": "ERROR",
            "error": str(e),
            "summary": f"Failed to process image: {str(e)}",
        }

        try:
            _update_checkpoint_result_sync(
                result_id=run_id,
                result=error_result,
                status=CheckStatus.failed,
            )
        except Exception as db_error:
            # If we can't even save the error to the database, log it
            # The run will stay in 'processing' status, indicating something went wrong
            logger.error(
                f"Failed to save error result for run {run_id}: {db_error}",
                exc_info=True,
            )


async def _compare_and_update_camera_runs_background(
    checkpoint: db.CheckPoint,
    image_urls: list[str],
    run_ids: list[UUID],
) -> None:
    """
    Background task: Compare multiple camera images against checkpoint and update runs.

    Processes images in batches of MAX_CONCURRENT_OPENAI_REQUESTS for parallel processing.
    Each batch sends N concurrent requests to OpenAI, waits for all to complete, then
    moves to the next batch. This balances speed (10x faster than sequential) with
    safety (stays within OpenAI rate limits).

    Args:
        checkpoint: The checkpoint to compare against (contains reference image and rules)
        image_urls: List of S3 presigned URLs for camera images (valid for 1 hour)
        run_ids: List of checkpoint run IDs to update (must match length of image_urls)

    Returns:
        None (updates database directly via _process_single_camera_image)

    Raises:
        ValueError: If image_urls and run_ids lengths don't match or inputs are empty
    """
    # Validate inputs to catch caller errors early
    if len(image_urls) != len(run_ids):
        raise ValueError(
            f"Mismatch: {len(image_urls)} image URLs but {len(run_ids)} run IDs"
        )

    if not image_urls:
        logger.warning("No images to process, exiting background task")
        return

    logger.info(
        f"Background task started: comparing {len(image_urls)} images "
        f"against checkpoint {checkpoint.id} "
        f"(batch size: {_constants.MAX_CONCURRENT_OPENAI_REQUESTS})"
    )

    total_images = len(image_urls)
    batch_size = _constants.MAX_CONCURRENT_OPENAI_REQUESTS

    # Process images in batches of N to balance speed vs OpenAI rate limits
    # Each batch runs N concurrent OpenAI API calls, then waits for all to complete
    for batch_start in range(0, total_images, batch_size):
        batch_end = min(batch_start + batch_size, total_images)
        batch_num = (batch_start // batch_size) + 1
        total_batches = (total_images + batch_size - 1) // batch_size

        logger.info(
            f"Processing batch {batch_num}/{total_batches} "
            f"(images {batch_start + 1}-{batch_end})"
        )

        # Create async tasks for this batch (will run concurrently)
        batch_tasks = [
            _process_single_camera_image(
                checkpoint=checkpoint,
                url=image_urls[idx],
                run_id=run_ids[idx],
                image_idx=idx + 1,
                total_images=total_images,
            )
            for idx in range(batch_start, batch_end)
        ]

        # Run all tasks in this batch concurrently
        # return_exceptions=True ensures one failure doesn't stop the batch
        await asyncio.gather(*batch_tasks, return_exceptions=True)

        logger.info(f"Completed batch {batch_num}/{total_batches}")

    logger.info(
        f"Background task completed: processed {len(image_urls)} images "
        f"for checkpoint {checkpoint.id}"
    )


def delete_checkpoint_run(session: Session, run_id: UUID) -> bool:
    """
    Delete a checkpoint run by run ID.

    Args:
        session: Database session
        run_id: UUID of the checkpoint run to delete

    Returns:
        bool: True if deleted, False if not found
    """
    return checkpoint_repository.delete_checkpoint_run(session, run_id)


def delete_checkpoint_runs_by_submission(session: Session, submission_id: UUID) -> int:
    """
    Delete all checkpoint runs for a given submission ID.

    Args:
        session: Database session
        submission_id: UUID of the submission

    Returns:
        int: Number of checkpoint runs deleted
    """
    return checkpoint_repository.delete_checkpoint_runs_by_submission(
        session, submission_id
    )
