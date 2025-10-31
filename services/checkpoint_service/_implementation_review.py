"""
Additional review-related functions for checkpoint service.
This file contains methods for updating checkpoint run review fields.
"""

from uuid import UUID

from sqlalchemy.orm import Session

import db
from db.repositories import checkpoint_repository


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
    return checkpoint_repository.update_checkpoint_run_review(
        session=session,
        run_id=run_id,
        review=review,
        reviewer=reviewer,
        is_reviewed=is_reviewed,
    )
