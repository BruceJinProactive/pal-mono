"""Routine Submission Repository.

Provides async database operations for routine submissions and item responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.routine_item_responses import RoutineItemResponse
from db.tables.routine_submissions import RoutineSubmission
from db.tables.types import ItemResponseStatus, SubmissionStatus
from utils.log import logger


class RoutineSubmissionRepositoryAsync:
    """Async repository for routine submission and item response operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========================================================================
    # Submission CRUD
    # ========================================================================

    async def create_submission(
        self,
        execution_id: uuid.UUID,
        status: SubmissionStatus = SubmissionStatus.draft,
        submitted_by: uuid.UUID | None = None,
    ) -> RoutineSubmission:
        """
        Create a new submission for an execution.

        Args:
            execution_id: Parent execution ID (1:1 relationship)
            status: Initial status (default: draft)
            submitted_by: Optional user ID who created the submission

        Returns:
            The created RoutineSubmission object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            submission = RoutineSubmission(
                execution_id=execution_id,
                status=status,
                submitted_by=submitted_by,
            )
            self.session.add(submission)
            await self.session.flush()
            await self.session.refresh(submission)
            return submission
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating submission: {e}")
            raise

    async def get_submission_by_id(
        self, submission_id: uuid.UUID
    ) -> RoutineSubmission | None:
        """
        Retrieve a submission by its ID.

        Args:
            submission_id: UUID of the submission

        Returns:
            RoutineSubmission object if found, None otherwise
        """
        try:
            stmt = select(RoutineSubmission).where(
                RoutineSubmission.id == submission_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting submission by id: {e}")
            return None

    async def get_submission_by_execution_id(
        self, execution_id: uuid.UUID
    ) -> RoutineSubmission | None:
        """
        Retrieve a submission by its execution ID.

        Since execution and submission have a 1:1 relationship,
        there should be at most one submission per execution.

        Args:
            execution_id: UUID of the execution

        Returns:
            RoutineSubmission object if found, None otherwise
        """
        try:
            stmt = select(RoutineSubmission).where(
                RoutineSubmission.execution_id == execution_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting submission by execution id: {e}")
            return None

    async def list_submissions_by_execution_ids(
        self,
        execution_ids: list[uuid.UUID],
    ) -> list[RoutineSubmission]:
        """
        List submissions for multiple executions.

        Args:
            execution_ids: List of execution IDs

        Returns:
            List of RoutineSubmission objects
        """
        try:
            if not execution_ids:
                return []

            stmt = (
                select(RoutineSubmission)
                .where(RoutineSubmission.execution_id.in_(execution_ids))
                .order_by(RoutineSubmission.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing submissions by execution ids: {e}")
            return []

    async def list_pending_review_submissions(
        self,
        execution_ids: list[uuid.UUID],
    ) -> list[RoutineSubmission]:
        """
        List submissions awaiting manager review.

        Args:
            execution_ids: List of execution IDs (from routines in the project)

        Returns:
            List of RoutineSubmission objects with status 'submitted'
        """
        try:
            if not execution_ids:
                return []

            stmt = (
                select(RoutineSubmission)
                .where(
                    RoutineSubmission.execution_id.in_(execution_ids),
                    RoutineSubmission.status == SubmissionStatus.submitted,
                )
                .order_by(RoutineSubmission.submitted_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing pending review submissions: {e}")
            return []

    async def update_submission(
        self,
        submission_id: uuid.UUID,
        status: SubmissionStatus | None = None,
        submitted_by: uuid.UUID | None = None,
        submitted_at: datetime | None = None,
        reviewed_by: uuid.UUID | None = None,
        reviewed_at: datetime | None = None,
        review_notes: str | None = None,
    ) -> RoutineSubmission | None:
        """
        Update a submission.

        Args:
            submission_id: UUID of the submission
            status: Optional new status
            submitted_by: Optional new submitted by user
            submitted_at: Optional new submitted at timestamp
            reviewed_by: Optional new reviewed by user
            reviewed_at: Optional new reviewed at timestamp
            review_notes: Optional new review notes

        Returns:
            Updated RoutineSubmission object if found, None otherwise
        """
        try:
            submission = await self.get_submission_by_id(submission_id)
            if not submission:
                return None

            if status is not None:
                submission.status = status
            if submitted_by is not None:
                submission.submitted_by = submitted_by
            if submitted_at is not None:
                submission.submitted_at = submitted_at
            if reviewed_by is not None:
                submission.reviewed_by = reviewed_by
            if reviewed_at is not None:
                submission.reviewed_at = reviewed_at
            if review_notes is not None:
                submission.review_notes = review_notes

            await self.session.flush()
            await self.session.refresh(submission)
            return submission
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating submission: {e}")
            return None

    async def delete_submission(self, submission_id: uuid.UUID) -> bool:
        """
        Delete a submission and its responses.

        Args:
            submission_id: UUID of the submission

        Returns:
            True if deleted, False if not found
        """
        try:
            submission = await self.get_submission_by_id(submission_id)
            if not submission:
                return False

            # Delete associated responses first
            responses = await self.list_responses_by_submission(submission_id)
            for response in responses:
                await self.session.delete(response)

            await self.session.delete(submission)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting submission: {e}")
            return False

    async def delete_submission_by_execution(self, execution_id: uuid.UUID) -> bool:
        """
        Delete the submission for an execution.

        Args:
            execution_id: UUID of the execution

        Returns:
            True if deleted, False if not found
        """
        try:
            submission = await self.get_submission_by_execution_id(execution_id)
            if not submission:
                return False

            return await self.delete_submission(submission.id)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting submission by execution: {e}")
            return False

    async def delete_submissions_by_execution_ids(
        self, execution_ids: list[uuid.UUID]
    ) -> int:
        """
        Delete all submissions for the given execution IDs.

        Also deletes associated item responses via bulk delete.

        Args:
            execution_ids: List of execution IDs

        Returns:
            Number of submissions deleted
        """
        try:
            if not execution_ids:
                return 0

            # First get submission IDs to delete item responses
            stmt = select(RoutineSubmission.id).where(
                RoutineSubmission.execution_id.in_(execution_ids)
            )
            result = await self.session.execute(stmt)
            submission_ids = [row[0] for row in result.fetchall()]

            if submission_ids:
                # Delete item responses first
                delete_responses = delete(RoutineItemResponse).where(
                    RoutineItemResponse.submission_id.in_(submission_ids)
                )
                await self.session.execute(delete_responses)

            # Delete submissions
            delete_submissions = delete(RoutineSubmission).where(
                RoutineSubmission.execution_id.in_(execution_ids)
            )
            result = await self.session.execute(delete_submissions)
            await self.session.flush()
            return result.rowcount
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting submissions by execution ids: {e}")
            return 0

    # ========================================================================
    # ItemResponse CRUD
    # ========================================================================

    async def create_item_response(
        self,
        submission_id: uuid.UUID,
        routine_item_id: uuid.UUID,
        image_url: str | None = None,
        notes: str | None = None,
        status: ItemResponseStatus = ItemResponseStatus.pending,
    ) -> RoutineItemResponse:
        """
        Create a new item response.

        Args:
            submission_id: Parent submission ID
            routine_item_id: ID of the routine item being responded to
            image_url: Optional S3 URL of uploaded image
            notes: Optional staff notes
            status: Initial status (default: pending)

        Returns:
            The created RoutineItemResponse object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            response = RoutineItemResponse(
                submission_id=submission_id,
                routine_item_id=routine_item_id,
                image_url=image_url,
                notes=notes,
                status=status,
            )
            self.session.add(response)
            await self.session.flush()
            await self.session.refresh(response)
            return response
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating item response: {e}")
            raise

    async def get_item_response_by_id(
        self, response_id: uuid.UUID
    ) -> RoutineItemResponse | None:
        """
        Retrieve an item response by its ID.

        Args:
            response_id: UUID of the response

        Returns:
            RoutineItemResponse object if found, None otherwise
        """
        try:
            stmt = select(RoutineItemResponse).where(
                RoutineItemResponse.id == response_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting item response by id: {e}")
            return None

    async def get_item_response_by_submission_and_item(
        self,
        submission_id: uuid.UUID,
        routine_item_id: uuid.UUID,
    ) -> RoutineItemResponse | None:
        """
        Retrieve an item response by submission and item ID.

        Due to the unique constraint, there's at most one response
        per submission/item combination.

        Args:
            submission_id: UUID of the submission
            routine_item_id: UUID of the routine item

        Returns:
            RoutineItemResponse object if found, None otherwise
        """
        try:
            stmt = select(RoutineItemResponse).where(
                RoutineItemResponse.submission_id == submission_id,
                RoutineItemResponse.routine_item_id == routine_item_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting item response by submission and item: {e}")
            return None

    async def list_responses_by_submission(
        self,
        submission_id: uuid.UUID,
    ) -> list[RoutineItemResponse]:
        """
        List all responses for a submission.

        Args:
            submission_id: UUID of the submission

        Returns:
            List of RoutineItemResponse objects
        """
        try:
            stmt = (
                select(RoutineItemResponse)
                .where(RoutineItemResponse.submission_id == submission_id)
                .order_by(RoutineItemResponse.created_at)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing responses by submission: {e}")
            return []

    async def update_item_response(
        self,
        response_id: uuid.UUID,
        image_url: str | None = None,
        notes: str | None = None,
        ai_result: Dict | None = None,
        ai_passed: bool | None = None,
        ai_confidence: Decimal | None = None,
        status: ItemResponseStatus | None = None,
    ) -> RoutineItemResponse | None:
        """
        Update an item response.

        Args:
            response_id: UUID of the response
            image_url: Optional new image URL
            notes: Optional new notes
            ai_result: Optional new AI result
            ai_passed: Optional new AI passed flag
            ai_confidence: Optional new AI confidence score
            status: Optional new status

        Returns:
            Updated RoutineItemResponse object if found, None otherwise
        """
        try:
            response = await self.get_item_response_by_id(response_id)
            if not response:
                return None

            if image_url is not None:
                response.image_url = image_url
            if notes is not None:
                response.notes = notes
            if ai_result is not None:
                response.ai_result = ai_result
            if ai_passed is not None:
                response.ai_passed = ai_passed
            if ai_confidence is not None:
                response.ai_confidence = ai_confidence
            if status is not None:
                response.status = status

            await self.session.flush()
            await self.session.refresh(response)
            return response
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating item response: {e}")
            return None

    async def upsert_item_response(
        self,
        submission_id: uuid.UUID,
        routine_item_id: uuid.UUID,
        image_url: str | None = None,
        notes: str | None = None,
        status: ItemResponseStatus = ItemResponseStatus.pending,
    ) -> RoutineItemResponse:
        """
        Create or update an item response.

        If a response already exists for this submission/item combination,
        update it. Otherwise, create a new one.

        Args:
            submission_id: Parent submission ID
            routine_item_id: ID of the routine item
            image_url: Optional S3 URL of uploaded image
            notes: Optional staff notes
            status: Status (default: pending)

        Returns:
            The created or updated RoutineItemResponse object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            existing = await self.get_item_response_by_submission_and_item(
                submission_id, routine_item_id
            )

            if existing:
                if image_url is not None:
                    existing.image_url = image_url
                if notes is not None:
                    existing.notes = notes
                existing.status = status
                await self.session.flush()
                await self.session.refresh(existing)
                return existing

            return await self.create_item_response(
                submission_id=submission_id,
                routine_item_id=routine_item_id,
                image_url=image_url,
                notes=notes,
                status=status,
            )
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error upserting item response: {e}")
            raise

    async def delete_item_response(self, response_id: uuid.UUID) -> bool:
        """
        Delete an item response by its ID.

        Args:
            response_id: UUID of the response

        Returns:
            True if deleted, False if not found
        """
        try:
            response = await self.get_item_response_by_id(response_id)
            if not response:
                return False

            await self.session.delete(response)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting item response: {e}")
            return False

    async def list_responses_by_submission_ids(
        self,
        submission_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[RoutineItemResponse]]:
        """
        List all responses for multiple submissions in a single query.

        Args:
            submission_ids: List of submission UUIDs

        Returns:
            Dict mapping submission_id to list of RoutineItemResponse objects
        """
        try:
            if not submission_ids:
                return {}

            stmt = (
                select(RoutineItemResponse)
                .where(RoutineItemResponse.submission_id.in_(submission_ids))
                .order_by(
                    RoutineItemResponse.submission_id, RoutineItemResponse.created_at
                )
            )
            result = await self.session.execute(stmt)
            responses = list(result.scalars().all())

            # Group responses by submission_id
            responses_by_submission: dict[uuid.UUID, list[RoutineItemResponse]] = {}
            for response in responses:
                if response.submission_id not in responses_by_submission:
                    responses_by_submission[response.submission_id] = []
                responses_by_submission[response.submission_id].append(response)

            return responses_by_submission
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing responses by submission ids: {e}")
            return {}
