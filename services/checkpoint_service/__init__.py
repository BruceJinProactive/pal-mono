from uuid import UUID

from sqlalchemy.orm import Session

import db

from . import _implementation


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
) -> "db.CheckpointResult":
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
) -> "db.CheckpointResult":
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
) -> "db.CheckpointResult":
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
) -> list["db.CheckpointResult"]:
    """
    List checkpoint results with optional filters.

    Args:
        session: Database session
        checkpoint_id: Optional filter by checkpoint ID
        submission_id: Optional filter by submission ID
        status: Optional filter by status

    Returns:
        List of checkpoint results
    """
    return _implementation.list_checkpoint_results(
        session, checkpoint_id, submission_id, status
    )


def get_checkpoint_result(
    session: Session,
    result_id: UUID,
) -> "db.CheckpointResult | None":
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
) -> "db.CheckpointResult":
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


__all__ = [
    "create_checkpoint",
    "list_checkpoints",
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
    "get_checkpoint_result",
    "update_checkpoint_result",
]
