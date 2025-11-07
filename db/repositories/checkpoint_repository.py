from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import CheckPoint, CheckpointRun
from db.tables.types import CheckStatus
from utils.log import logger

# Decoupled database functions (functional approach)


def create_checkpoint(session: Session, checkpoint: CheckPoint) -> CheckPoint:
    """Create a new checkpoint in the database."""
    # Validate required fields
    if not checkpoint.project_id:
        raise ValueError("project_id is required and cannot be empty")
    if not checkpoint.name or not checkpoint.name.strip():
        raise ValueError("name is required and cannot be empty")

    # Explicitly copy allowed fields to avoid SQLAlchemy internals
    db_checkpoint = CheckPoint(
        project_id=checkpoint.project_id,
        checklist_id=checkpoint.checklist_id,
        name=checkpoint.name,
        description=checkpoint.description,
        image_url=checkpoint.image_url,
        is_active=(checkpoint.is_active if checkpoint.is_active is not None else False),
        group=checkpoint.group,
        rules=checkpoint.rules,
        requires_image=(
            checkpoint.requires_image
            if checkpoint.requires_image is not None
            else False
        ),
    )

    try:
        session.add(db_checkpoint)
        session.commit()
        session.refresh(db_checkpoint)
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error creating checkpoint: {e}")
        raise

    return db_checkpoint


def list_checkpoints(session: Session, project_id: UUID) -> list[CheckPoint]:
    """Get all checkpoints for a project."""
    try:
        checkpoints = (
            session.query(CheckPoint).filter(CheckPoint.project_id == project_id).all()
        )
        return checkpoints
    except SQLAlchemyError as e:
        logger.error(f"Error listing checkpoints: {e}")
        raise


def list_checkpoints_by_checklist(
    session: Session, checklist_id: UUID
) -> list[CheckPoint]:
    """Get all checkpoints for a checklist."""
    try:
        checkpoints = (
            session.query(CheckPoint)
            .filter(CheckPoint.checklist_id == checklist_id)
            .all()
        )
        return checkpoints
    except SQLAlchemyError as e:
        logger.error(f"Error listing checkpoints by checklist: {e}")
        raise


def list_active_checkpoints_by_checklist_before_date(
    session: Session,
    checklist_id: UUID,
    end_date: datetime,
) -> list[CheckPoint]:
    """
    Get all active checkpoints for a checklist that existed on or before a specific date.

    This is used for historically accurate views - only returns checkpoints that:
    1. Belong to the specified checklist
    2. Are active (is_active=true)
    3. Were created on or before the specified date

    Args:
        session: Database session
        checklist_id: UUID of the checklist
        end_date: Only return checkpoints created on or before this date

    Returns:
        list[CheckPoint]: List of active checkpoints that existed on that date
    """
    try:
        checkpoints = (
            session.query(CheckPoint)
            .filter(
                CheckPoint.checklist_id == checklist_id,
                CheckPoint.is_active.is_(True),
                CheckPoint.created_at <= end_date,
            )
            .all()
        )
        return checkpoints
    except SQLAlchemyError as e:
        logger.error(f"Error listing active checkpoints by checklist before date: {e}")
        raise


def get_checkpoint(session: Session, checkpoint_id: UUID) -> CheckPoint | None:
    """Get a checkpoint by ID."""
    try:
        checkpoint = (
            session.query(CheckPoint).filter(CheckPoint.id == checkpoint_id).first()
        )
        return checkpoint
    except SQLAlchemyError as e:
        logger.error(f"Error getting checkpoint: {e}")
        raise


def update_checkpoint(
    session: Session, checkpoint_id: UUID, updates: dict
) -> CheckPoint | None:
    """Update a checkpoint by ID. Returns updated checkpoint or None if not found."""
    try:
        checkpoint = get_checkpoint(session, checkpoint_id)
        if not checkpoint:
            return None

        # Update only whitelisted fields
        allowed = {
            "name",
            "description",
            "image_url",
            "is_active",
            "group",
            "rules",
            "checklist_id",
            "requires_image",
        }
        # Fields that can be explicitly set to None
        nullable_fields = {"description", "image_url", "group", "rules", "checklist_id"}

        for key, value in updates.items():
            if key in allowed:
                # Allow None values for nullable fields, skip None for required fields
                if value is not None or key in nullable_fields:
                    setattr(checkpoint, key, value)

        session.commit()
        session.refresh(checkpoint)
        return checkpoint
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating checkpoint: {e}")
        raise


def delete_checkpoint(session: Session, checkpoint_id: UUID) -> bool:
    """Delete a checkpoint by ID. Returns True if deleted, False if not found."""
    try:
        checkpoint = get_checkpoint(session, checkpoint_id)
        if not checkpoint:
            return False

        session.delete(checkpoint)
        session.commit()
        return True
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error deleting checkpoint: {e}")
        raise


def get_checkpoint_by_camera_name(
    session: Session, project_id: UUID, camera_name: str
) -> CheckPoint | None:
    """Get a checkpoint by camera name within a project."""
    try:
        checkpoint = (
            session.query(CheckPoint)
            .filter(
                CheckPoint.project_id == project_id,
                CheckPoint.name == camera_name,
            )
            .first()
        )
        return checkpoint
    except SQLAlchemyError as e:
        logger.error(f"Error getting checkpoint by camera name: {e}")
        raise


def get_checkpoint_by_camera_name_and_checklist(
    session: Session, checklist_id: UUID, camera_name: str
) -> CheckPoint | None:
    """Get a checkpoint by camera name within a checklist."""
    try:
        checkpoint = (
            session.query(CheckPoint)
            .filter(
                CheckPoint.checklist_id == checklist_id,
                CheckPoint.name == camera_name,
            )
            .first()
        )
        return checkpoint
    except SQLAlchemyError as e:
        logger.error(f"Error getting checkpoint by camera name and checklist: {e}")
        raise


# Legacy class-based repository (kept for backwards compatibility)


class CheckpointRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_checkpoint(self, checkpoint: CheckPoint) -> CheckPoint:
        return create_checkpoint(self.session, checkpoint)

    def list_checkpoints(self, project_id: UUID) -> list[CheckPoint]:
        return list_checkpoints(self.session, project_id)

    def list_checkpoints_by_checklist(self, checklist_id: UUID) -> list[CheckPoint]:
        return list_checkpoints_by_checklist(self.session, checklist_id)

    def get_checkpoint(self, checkpoint_id: UUID) -> CheckPoint | None:
        return get_checkpoint(self.session, checkpoint_id)

    def update_checkpoint(
        self, checkpoint_id: UUID, updates: dict
    ) -> CheckPoint | None:
        return update_checkpoint(self.session, checkpoint_id, updates)

    def delete_checkpoint(self, checkpoint_id: UUID) -> bool:
        return delete_checkpoint(self.session, checkpoint_id)


# Checkpoint Result functions


def create_checkpoint_result_processing(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
) -> CheckpointRun:
    """
    Create a checkpoint result with 'processing' status immediately.
    This is called BEFORE OpenAI starts processing.

    Args:
        session: Database session
        checkpoint_id: UUID of the checkpoint
        submission_id: UUID of the submission being checked

    Returns:
        CheckpointResult: The created checkpoint result record with processing status
    """
    try:
        checkpoint_result = CheckpointRun(
            checkpoint_id=checkpoint_id,
            submission_id=submission_id,
            result={},  # Empty initially
            status=CheckStatus.processing,
        )

        session.add(checkpoint_result)
        session.commit()
        session.refresh(checkpoint_result)

        logger.info(
            f"Created checkpoint result {checkpoint_result.id} with status 'processing' "
            f"for checkpoint {checkpoint_id}, submission {submission_id}"
        )

        return checkpoint_result
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error creating checkpoint result: {e}")
        raise


def list_checkpoint_results(
    session: Session,
    checkpoint_id: UUID | None = None,
    submission_id: UUID | None = None,
    status: CheckStatus | None = None,
    project_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[CheckpointRun]:
    """
    List checkpoint results with optional filters.

    Args:
        session: Database session
        checkpoint_id: Optional filter by checkpoint ID
        submission_id: Optional filter by submission ID
        status: Optional filter by status
        project_id: Optional filter by project ID (via checkpoint)
        start_date: Optional filter by created_at >= start_date (datetime object)
        end_date: Optional filter by created_at <= end_date (datetime object)

    Returns:
        list[CheckpointRun]: List of checkpoint results
    """
    try:
        query = session.query(CheckpointRun)

        # Join with CheckPoint table if we need to filter by project_id
        if project_id:
            query = query.join(CheckPoint, CheckpointRun.checkpoint_id == CheckPoint.id)
            query = query.filter(CheckPoint.project_id == project_id)

        if checkpoint_id:
            query = query.filter(CheckpointRun.checkpoint_id == checkpoint_id)

        if submission_id:
            query = query.filter(CheckpointRun.submission_id == submission_id)

        if status:
            query = query.filter(CheckpointRun.status == status)

        if start_date:
            query = query.filter(CheckpointRun.created_at >= start_date)

        if end_date:
            query = query.filter(CheckpointRun.created_at <= end_date)

        # Order by created_at descending (newest first)
        query = query.order_by(CheckpointRun.created_at.desc())

        return query.all()
    except SQLAlchemyError as e:
        logger.error(f"Error listing checkpoint results: {e}")
        raise


def get_checkpoint_result(
    session: Session,
    result_id: UUID,
) -> CheckpointRun | None:
    """
    Get a single checkpoint result by ID.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result

    Returns:
        CheckpointRun | None: The checkpoint result or None if not found
    """
    try:
        return (
            session.query(CheckpointRun).filter(CheckpointRun.id == result_id).first()
        )
    except SQLAlchemyError as e:
        logger.error(f"Error getting checkpoint result: {e}")
        raise


def update_checkpoint_result(
    session: Session,
    result_id: UUID,
    result: dict,
    status: CheckStatus,
) -> CheckpointRun:
    """
    Update a checkpoint result with the final comparison result.
    This is called AFTER OpenAI finishes processing.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result to update
        result: Dictionary containing the comparison result (JSON)
        status: Final status (active or failed)

    Returns:
        CheckpointRun: The updated checkpoint result record

    Raises:
        ValueError: If checkpoint result not found
    """
    try:
        checkpoint_result = (
            session.query(CheckpointRun).filter(CheckpointRun.id == result_id).first()
        )

        if not checkpoint_result:
            raise ValueError(f"CheckpointRun {result_id} not found")

        checkpoint_result.result = result
        checkpoint_result.status = status

        session.commit()
        session.refresh(checkpoint_result)

        logger.info(
            f"Updated checkpoint result {result_id} with status '{status.value}', "
            f"overall_result: {result.get('overall_result', 'N/A')}"
        )

        return checkpoint_result
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating checkpoint result: {e}")
        raise


def save_checkpoint_result(
    session: Session,
    checkpoint_id: UUID,
    submission_id: UUID,
    result: dict,
    status: CheckStatus = CheckStatus.active,
) -> CheckpointRun:
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
        CheckpointResult: The created checkpoint result record
    """
    try:
        checkpoint_result = CheckpointRun(
            checkpoint_id=checkpoint_id,
            submission_id=submission_id,
            result=result,
            status=status,
        )

        session.add(checkpoint_result)
        session.commit()
        session.refresh(checkpoint_result)

        logger.info(
            f"Saved checkpoint result {checkpoint_result.id} for checkpoint {checkpoint_id}, "
            f"submission {submission_id}, status: {status.value}"
        )

        return checkpoint_result
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error saving checkpoint result: {e}")
        raise


def update_checkpoint_run_review(
    session: Session,
    run_id: UUID,
    review: str | None = None,
    reviewer: str | None = None,
    is_reviewed: bool | None = None,
) -> CheckpointRun:
    """
    Update review fields of a checkpoint run.

    Args:
        session: Database session
        run_id: UUID of the checkpoint run to update
        review: Optional review comments/notes
        reviewer: Optional reviewer name or email
        is_reviewed: Optional reviewed status flag

    Returns:
        CheckpointRun: The updated checkpoint run record

    Raises:
        ValueError: If checkpoint run not found
    """
    try:
        checkpoint_run = (
            session.query(CheckpointRun).filter(CheckpointRun.id == run_id).first()
        )

        if not checkpoint_run:
            raise ValueError(f"CheckpointRun {run_id} not found")

        # Update only provided fields
        if review is not None:
            checkpoint_run.review = review
        if reviewer is not None:
            checkpoint_run.reviewer = reviewer
        if is_reviewed is not None:
            checkpoint_run.is_reviewed = is_reviewed

        session.commit()
        session.refresh(checkpoint_run)

        logger.info(
            f"Updated checkpoint run {run_id} review fields: "
            f"is_reviewed={checkpoint_run.is_reviewed}, reviewer={checkpoint_run.reviewer}"
        )

        return checkpoint_run
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error updating checkpoint run review: {e}")
        raise


def delete_checkpoint_run(
    session: Session,
    run_id: UUID,
) -> bool:
    """
    Delete a checkpoint run by run ID.

    Args:
        session: Database session
        run_id: UUID of the checkpoint run to delete

    Returns:
        bool: True if deleted, False if not found
    """
    try:
        checkpoint_run = (
            session.query(CheckpointRun).filter(CheckpointRun.id == run_id).first()
        )

        if not checkpoint_run:
            return False

        session.delete(checkpoint_run)
        session.commit()

        logger.info(f"Deleted checkpoint run {run_id}")
        return True
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error deleting checkpoint run: {e}")
        raise


def delete_checkpoint_runs_by_submission(
    session: Session,
    submission_id: UUID,
) -> int:
    """
    Delete all checkpoint runs for a given submission ID.

    Args:
        session: Database session
        submission_id: UUID of the submission

    Returns:
        int: Number of checkpoint runs deleted
    """
    try:
        # Get all runs with this submission_id
        runs = (
            session.query(CheckpointRun)
            .filter(CheckpointRun.submission_id == submission_id)
            .all()
        )

        if not runs:
            return 0

        count = len(runs)

        # Delete all runs
        for run in runs:
            session.delete(run)

        session.commit()

        logger.info(f"Deleted {count} checkpoint runs for submission {submission_id}")
        return count
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error deleting checkpoint runs by submission: {e}")
        raise
