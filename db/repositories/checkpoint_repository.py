from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables import CheckPoint, CheckpointResult
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
        name=checkpoint.name,
        description=checkpoint.description,
        image_url=checkpoint.image_url,
        is_active=(checkpoint.is_active if checkpoint.is_active is not None else False),
        group=checkpoint.group,
        rules=checkpoint.rules,
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
        allowed = {"name", "description", "image_url", "is_active", "group", "rules"}
        for key, value in updates.items():
            if key in allowed and value is not None:
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


# Legacy class-based repository (kept for backwards compatibility)


class CheckpointRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_checkpoint(self, checkpoint: CheckPoint) -> CheckPoint:
        return create_checkpoint(self.session, checkpoint)

    def list_checkpoints(self, project_id: UUID) -> list[CheckPoint]:
        return list_checkpoints(self.session, project_id)

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
) -> CheckpointResult:
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
        checkpoint_result = CheckpointResult(
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
) -> list[CheckpointResult]:
    """
    List checkpoint results with optional filters.

    Args:
        session: Database session
        checkpoint_id: Optional filter by checkpoint ID
        submission_id: Optional filter by submission ID
        status: Optional filter by status
        project_id: Optional filter by project ID (via checkpoint)

    Returns:
        list[CheckpointResult]: List of checkpoint results
    """
    try:
        query = session.query(CheckpointResult)

        # Join with CheckPoint table if we need to filter by project_id
        if project_id:
            query = query.join(
                CheckPoint, CheckpointResult.checkpoint_id == CheckPoint.id
            )
            query = query.filter(CheckPoint.project_id == project_id)

        if checkpoint_id:
            query = query.filter(CheckpointResult.checkpoint_id == checkpoint_id)

        if submission_id:
            query = query.filter(CheckpointResult.submission_id == submission_id)

        if status:
            query = query.filter(CheckpointResult.status == status)

        # Order by created_at descending (newest first)
        query = query.order_by(CheckpointResult.created_at.desc())

        return query.all()
    except SQLAlchemyError as e:
        logger.error(f"Error listing checkpoint results: {e}")
        raise


def get_checkpoint_result(
    session: Session,
    result_id: UUID,
) -> CheckpointResult | None:
    """
    Get a single checkpoint result by ID.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result

    Returns:
        CheckpointResult | None: The checkpoint result or None if not found
    """
    try:
        return (
            session.query(CheckpointResult)
            .filter(CheckpointResult.id == result_id)
            .first()
        )
    except SQLAlchemyError as e:
        logger.error(f"Error getting checkpoint result: {e}")
        raise


def update_checkpoint_result(
    session: Session,
    result_id: UUID,
    result: dict,
    status: CheckStatus,
) -> CheckpointResult:
    """
    Update a checkpoint result with the final comparison result.
    This is called AFTER OpenAI finishes processing.

    Args:
        session: Database session
        result_id: UUID of the checkpoint result to update
        result: Dictionary containing the comparison result (JSON)
        status: Final status (active or failed)

    Returns:
        CheckpointResult: The updated checkpoint result record

    Raises:
        ValueError: If checkpoint result not found
    """
    try:
        checkpoint_result = (
            session.query(CheckpointResult)
            .filter(CheckpointResult.id == result_id)
            .first()
        )

        if not checkpoint_result:
            raise ValueError(f"CheckpointResult {result_id} not found")

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
) -> CheckpointResult:
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
        checkpoint_result = CheckpointResult(
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
