from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

import db

from . import _implementation, _implementation_review


def create_checkpoint(session: Session, checkpoint: db.CheckPoint) -> db.CheckPoint:
    """
    Create a new checkpoint in the database.

    Args:
        session (Session): The database session to use for the transaction.
        checkpoint (db.CheckPoint): The checkpoint object to create.

    Returns:
        db.CheckPoint: The created checkpoint with database-generated fields.
    """
    return _implementation.create_checkpoint(session, checkpoint)


def list_checkpoints(session: Session, project_id: UUID) -> list[db.CheckPoint]:
    """
    List all checkpoints for a project.

    Args:
        session (Session): The database session to use for the query.
        project_id (UUID): The UUID of the project.

    Returns:
        list[db.CheckPoint]: List of checkpoints for the project.
    """
    return _implementation.list_checkpoints(session, project_id)


def list_checkpoints_by_checklist(
    session: Session, checklist_id: UUID
) -> list[db.CheckPoint]:
    """
    List all checkpoints for a checklist.

    Args:
        session (Session): The database session to use for the query.
        checklist_id (UUID): The UUID of the checklist.

    Returns:
        list[db.CheckPoint]: List of checkpoints for the checklist.
    """
    return _implementation.list_checkpoints_by_checklist(session, checklist_id)


def get_checkpoint(session: Session, checkpoint_id: UUID) -> db.CheckPoint | None:
    """
    Get a checkpoint by ID.

    Args:
        session (Session): The database session to use for the query.
        checkpoint_id (UUID): The UUID of the checkpoint.

    Returns:
        db.CheckPoint | None: The checkpoint if found, None otherwise.
    """
    return _implementation.get_checkpoint(session, checkpoint_id)


def update_checkpoint(
    session: Session, checkpoint_id: UUID, updates: dict
) -> db.CheckPoint | None:
    """
    Update a checkpoint by ID.

    Args:
        session (Session): The database session to use for the transaction.
        checkpoint_id (UUID): The UUID of the checkpoint to update.
        updates (dict): Dictionary of fields to update.

    Returns:
        db.CheckPoint | None: The updated checkpoint if found, None otherwise.
    """
    return _implementation.update_checkpoint(session, checkpoint_id, updates)


def delete_checkpoint(session: Session, checkpoint_id: UUID) -> bool:
    """
    Delete a checkpoint by ID.

    Args:
        session (Session): The database session to use for the transaction.
        checkpoint_id (UUID): The UUID of the checkpoint to delete.

    Returns:
        bool: True if the checkpoint was deleted, False if not found.
    """
    return _implementation.delete_checkpoint(session, checkpoint_id)


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
        Dictionary containing comparison results with structured JSON including:
        - overall_result: "PASS" or "FAIL"
        - cleanliness_issues: List of issues found
        - rule_violations: Detailed rule-by-rule analysis
        - recommendation: Pass/fail recommendation

    Raises:
        Exception: If S3 retrieval or OpenAI API call fails
    """
    return _implementation.compare_checkpoint_images(checkpoint, uploaded_image_base64)


async def compare_checkpoint_images_async(
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> dict:
    """
    Async version: Compare an uploaded image with a checkpoint's reference image.

    Args:
        checkpoint: The checkpoint database object with image_url and rules
        uploaded_image_base64: Base64 encoded string of the uploaded image

    Returns:
        Dictionary containing comparison results with structured JSON

    Raises:
        Exception: If S3 retrieval or OpenAI API call fails
    """
    return await _implementation.compare_checkpoint_images_async(
        checkpoint, uploaded_image_base64
    )


def save_checkpoint_result(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
    result: dict,
    status: "db.tables.types.CheckStatus",
) -> "db.CheckpointRun":
    """
    Save a checkpoint comparison result to the database.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked
        result: Dictionary containing the comparison result
        status: Status of the check

    Returns:
        The created checkpoint result record
    """
    return _implementation.save_checkpoint_result(
        session, checkpoint_id, submission_id, result, status
    )


async def compare_and_save_checkpoint_async(
    session: Session,
    checkpoint: db.CheckPoint,
    submission_id: UUID,
    uploaded_image_base64: str,
) -> "db.CheckpointRun":
    """
    Async function to compare checkpoint images and save the result.

    This function runs the comparison asynchronously and saves the result to the database.
    Can be used to process multiple checkpoints concurrently.

    Args:
        session: Database session
        checkpoint: The checkpoint to compare against
        submission_id: UUID of the submission being checked
        uploaded_image_base64: Base64 encoded uploaded image

    Returns:
        The saved checkpoint result
    """
    return await _implementation.compare_and_save_checkpoint_async(
        session, checkpoint, submission_id, uploaded_image_base64
    )


async def compare_and_update_checkpoint_background(
    checkpoint_result_id: UUID,
    checkpoint: db.CheckPoint,
    uploaded_image_base64: str,
) -> None:
    """
    Background task: Compare images and update existing checkpoint result.

    This function runs in the background and updates the checkpoint_result
    from 'processing' to 'active' or 'failed'.

    This function creates a new short-lived Session using SyncSessionLocal to avoid
    reusing the request-scoped Session which may have been closed.

    Args:
        checkpoint_result_id: UUID of the checkpoint result to update
        checkpoint: The checkpoint to compare against
        uploaded_image_base64: Base64 encoded uploaded image

    Returns:
        None (updates database directly)
    """
    return await _implementation.compare_and_update_checkpoint_background(
        checkpoint_result_id, checkpoint, uploaded_image_base64
    )


def create_checkpoint_result_processing(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
) -> "db.CheckpointRun":
    """
    Create a checkpoint result with 'processing' status immediately.
    This is called BEFORE OpenAI starts processing.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked

    Returns:
        The created checkpoint result record with processing status
    """
    return _implementation.create_checkpoint_result_processing(
        session, checkpoint_id, submission_id
    )


def list_checkpoint_results(
    session: Session,
    checkpoint_id: UUID | None = None,
    submission_id: UUID | None = None,
    status: "db.tables.types.CheckStatus | None" = None,
    project_id: UUID | None = None,
    start_date: "datetime | None" = None,
    end_date: "datetime | None" = None,
) -> list["db.CheckpointRun"]:
    """
    List checkpoint results with optional filters.

    Args:
        session: Database session
        checkpoint_id: Optional filter by checkpoint ID
        submission_id: Optional filter by submission ID
        status: Optional filter by status
        project_id: Optional filter by project ID (via checkpoint)
        start_date: Optional filter by created_at >= start_date
        end_date: Optional filter by created_at <= end_date

    Returns:
        List of checkpoint results
    """
    return _implementation.list_checkpoint_results(
        session, checkpoint_id, submission_id, status, project_id, start_date, end_date
    )


def get_latest_checkpoint_result_by_date_range(
    session: Session,
    checkpoint_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> "db.CheckpointRun | None":
    """
    Get the latest checkpoint result for a specific checkpoint, filtered by date range.
    Returns only the most recent result (by created_at) within the date range.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        start_date: Optional start date filter (datetime object)
        end_date: Optional end date filter (datetime object)

    Returns:
        The latest checkpoint result or None if not found
    """
    return _implementation.get_latest_checkpoint_result_by_date_range(
        session, checkpoint_id, start_date, end_date
    )


def get_checkpoint_result(
    session: Session,
    result_id: UUID,
) -> "db.CheckpointRun | None":
    """
    Get a single checkpoint result by ID.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result

    Returns:
        The checkpoint result or None if not found
    """
    return _implementation.get_checkpoint_result(session, result_id)


def update_checkpoint_result(
    session: Session,
    result_id: UUID,
    result: dict,
    status: "db.tables.types.CheckStatus",
) -> "db.CheckpointRun":
    """
    Update a checkpoint result with the final comparison result.
    This is called AFTER OpenAI finishes processing.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result to update
        result: Dictionary containing the comparison result (JSON)
        status: Final status (active or failed)

    Returns:
        The updated checkpoint result record
    """
    return _implementation.update_checkpoint_result(session, result_id, result, status)


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
    return _implementation.record_checkpoint_run(
        session, checkpoint_id, status_value, image_url
    )


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
    return _implementation.update_checkpoint_run_image(session, run_id, image_url)


def update_checkpoint_run_review(
    session: Session,
    run_id: UUID,
    review: str | None = None,
    reviewer: str | None = None,
    is_reviewed: bool | None = None,
) -> db.CheckpointRun:
    """
    Update review fields of a checkpoint run.

    Args:
        session: Database session
        run_id: UUID of the checkpoint run to update
        review: Optional review comments/notes
        reviewer: Optional reviewer name or email
        is_reviewed: Optional reviewed status flag

    Returns:
        db.CheckpointRun: The updated checkpoint run record

    Raises:
        ValueError: If run not found
    """
    return _implementation_review.update_checkpoint_run_review(
        session, run_id, review, reviewer, is_reviewed
    )


def compare_camera_images_with_checkpoint(
    session: Session,
    checkpoint: db.CheckPoint,
    start_time: datetime,
    end_time: datetime,
) -> dict:
    """
    Retrieve S3 images for a checkpoint and compare them against the checkpoint reference.

    Creates checkpoint runs with 'processing' status immediately and starts background comparison.
    All runs in a batch share the same submission_id.

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
    return _implementation.compare_camera_images_with_checkpoint(
        session, checkpoint, start_time, end_time
    )


def get_checkpoint_results_by_ids(
    session: Session, result_ids: list[UUID]
) -> list[db.CheckpointRun]:
    """
    Get multiple checkpoint results by their IDs in a single query.

    Args:
        session: Database session
        result_ids: List of UUIDs of checkpoint results

    Returns:
        list[db.CheckpointRun]: List of checkpoint results
    """
    return _implementation.get_checkpoint_results_by_ids(session, result_ids)


def delete_checkpoint_runs(session: Session, run_ids: list[UUID]) -> int:
    """
    Delete multiple checkpoint runs by their run IDs (batch delete).

    Args:
        session: Database session
        run_ids: List of UUIDs of checkpoint runs to delete

    Returns:
        int: Number of checkpoint runs deleted
    """
    return _implementation.delete_checkpoint_runs(session, run_ids)


__all__ = [
    "create_checkpoint",
    "list_checkpoints",
    "list_checkpoints_by_checklist",
    "get_checkpoint",
    "update_checkpoint",
    "delete_checkpoint",
    "compare_checkpoint_images",
    "compare_checkpoint_images_async",
    "save_checkpoint_result",
    "compare_and_save_checkpoint_async",
    "compare_and_update_checkpoint_background",
    "create_checkpoint_result_processing",
    "list_checkpoint_results",
    "get_latest_checkpoint_result_by_date_range",
    "get_checkpoint_result",
    "get_checkpoint_results_by_ids",
    "update_checkpoint_result",
    "record_checkpoint_run",
    "update_checkpoint_run_image",
    "update_checkpoint_run_review",
    "compare_camera_images_with_checkpoint",
    "delete_checkpoint_runs",
]
