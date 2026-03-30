import uuid
from datetime import date, datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import CateringRequest
from db.tables.catering_requests import RequestStatus
from utils.log import logger


class CateringRequestRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_catering_request(
        self, catering_request: CateringRequest
    ) -> CateringRequest:
        """
        Create a new catering request asynchronously.
        Args:
            catering_request (CateringRequest): The catering request object to create.
        Returns:
            CateringRequest: The created or existing catering request.
        """
        db_catering_request = CateringRequest()
        for key, value in vars(catering_request).items():
            if (
                hasattr(CateringRequest, key)
                and key
                not in {
                    "id",
                    "created_at",
                    "updated_at",
                }
                and value is not None
            ):  # Ignore None values to avoid constraint violations
                setattr(db_catering_request, key, value)

        try:
            self.session.add(db_catering_request)
            await self.session.commit()
            await self.session.refresh(db_catering_request)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating catering request: {e}")
            raise

        return db_catering_request

    async def get_catering_request_by_id(
        self, catering_request_id: uuid.UUID
    ) -> CateringRequest | None:
        """
        Get catering request by ID asynchronously.

        Args:
            catering_request_id (uuid.UUID): The ID of the catering request to retrieve.

        Returns:
            CateringRequest | None: The catering request if found, None otherwise.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.id == catering_request_id
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving catering request by ID {catering_request_id}: {e}"
            )
            raise

    async def list_catering_requests_by_project_id(
        self, project_id: uuid.UUID
    ) -> List[CateringRequest]:
        """
        List all catering requests for a specific project asynchronously.
        Args:
            project_id (uuid.UUID): The project ID to filter by.
        Returns:
            List[CateringRequest]: List of catering requests for the project.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.project_id == project_id
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(
                f"Error retrieving catering requests for project {project_id}: {e}"
            )
            raise

    async def list_inquiry_requests_in_date_range(
        self,
        created_after: datetime,
        created_before: datetime,
    ) -> list[CateringRequest]:
        """
        List all INQUIRY catering requests created within a UTC date range.

        Args:
            created_after: Start of the UTC window (inclusive).
            created_before: End of the UTC window (exclusive).

        Returns:
            list[CateringRequest]: Matching catering requests.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.status == RequestStatus.INQUIRY,
                CateringRequest.created_at >= created_after,
                CateringRequest.created_at < created_before,
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing inquiry requests in date range: {e}")
            raise

    async def list_inquiry_requests_by_event_date_range(
        self,
        event_date_start: date,
        event_date_end: date,
    ) -> list[CateringRequest]:
        """
        List all INQUIRY catering requests whose event_date falls within a range.

        Args:
            event_date_start: Start of the event date range (inclusive).
            event_date_end: End of the event date range (inclusive).

        Returns:
            list[CateringRequest]: Matching catering requests.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.status == RequestStatus.INQUIRY,
                CateringRequest.event_date >= event_date_start,
                CateringRequest.event_date <= event_date_end,
            )
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing inquiry requests by event date range: {e}")
            raise

    async def update_catering_request(
        self, catering_request_id: uuid.UUID, updated_catering_request: CateringRequest
    ) -> CateringRequest:
        """
        Update an existing catering request by ID asynchronously.
        Args:
            catering_request_id (uuid.UUID): The ID of the catering request to update.
            updated_catering_request (CateringRequest): The updated catering request data.
        Returns:
            CateringRequest: The updated catering request.
        Raises:
            ValueError: If the catering request is not found.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.id == catering_request_id
            )
            result = await self.session.execute(query)
            db_catering_request = result.scalar_one_or_none()

            if db_catering_request is None:
                raise ValueError(f"Catering request {catering_request_id} not found")

            for key, value in vars(updated_catering_request).items():
                if (
                    hasattr(CateringRequest, key)
                    and key
                    not in {
                        "id",
                        "created_at",
                        "updated_at",
                        "idempotency_key",  # Block idempotency_key updates to preserve deduplication
                    }
                    and value is not None
                ):  # Ignore None values to avoid constraint violations
                    setattr(db_catering_request, key, value)

            await self.session.commit()
            await self.session.refresh(db_catering_request)
            return db_catering_request
        except (SQLAlchemyError, ValueError) as e:
            await self.session.rollback()
            logger.error(f"Error updating catering request: {e}")
            raise
        except Exception as e:
            await self.session.rollback()
            logger.exception(
                f"Unexpected error while updating catering request {catering_request_id}: {e}"
            )
            raise


class CateringRequestRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_catering_request(
        self, catering_request: CateringRequest
    ) -> CateringRequest:
        """
        Create a new catering request synchronously with idempotency check.
        If a request with the same idempotency_key exists, return that instead.
        Args:
            catering_request (CateringRequest): The catering request object to create.
        Returns:
            CateringRequest: The created or existing catering request.
        """
        # First check if request with this idempotency key already exists
        if catering_request.idempotency_key:
            existing_request = self.get_catering_request_by_idempotency_key(
                catering_request.idempotency_key
            )
            if existing_request:
                logger.info(
                    f"Returning existing catering request for idempotency key: {catering_request.idempotency_key}"
                )
                return existing_request

        # If no existing request, create new one
        db_catering_request = CateringRequest()
        for key, value in vars(catering_request).items():
            if (
                hasattr(CateringRequest, key)
                and key
                not in {
                    "id",
                    "created_at",
                    "updated_at",
                }
                and value is not None
            ):  # Ignore None values to avoid constraint violations
                setattr(db_catering_request, key, value)

        try:
            self.session.add(db_catering_request)
            self.session.commit()
            self.session.refresh(db_catering_request)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating catering request: {e}")
            raise

        return db_catering_request

    def get_catering_request_by_idempotency_key(
        self, idempotency_key: str
    ) -> CateringRequest | None:
        """
        Get catering request by idempotency key synchronously.
        Args:
            idempotency_key (str): The idempotency key to search for.
        Returns:
            CateringRequest: The catering request if found, None otherwise.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.idempotency_key == idempotency_key
            )
            result = self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving catering request by idempotency key: {e}")
            raise

    def list_catering_requests_by_project_id(
        self, project_id: uuid.UUID
    ) -> List[CateringRequest]:
        """
        List all catering requests for a specific project synchronously.
        Args:
            project_id (uuid.UUID): The project ID to filter by.
        Returns:
            List[CateringRequest]: List of catering requests for the project.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.project_id == project_id
            )
            result = self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                f"Error retrieving catering requests for project {project_id}: {e}"
            )
            raise

    def update_catering_request(
        self, catering_request_id: uuid.UUID, updated_catering_request: CateringRequest
    ) -> CateringRequest:
        """
        Update an existing catering request by ID synchronously.
        Args:
            catering_request_id (uuid.UUID): The ID of the catering request to update.
            updated_catering_request (CateringRequest): The updated catering request data.
        Returns:
            CateringRequest: The updated catering request.
        Raises:
            ValueError: If the catering request is not found.
        """
        try:
            query = select(CateringRequest).filter(
                CateringRequest.id == catering_request_id
            )
            result = self.session.execute(query)
            db_catering_request = result.scalar_one_or_none()

            if db_catering_request is None:
                raise ValueError(f"Catering request {catering_request_id} not found")

            # Update fields from the provided catering request
            for key, value in vars(updated_catering_request).items():
                if (
                    hasattr(CateringRequest, key)
                    and key
                    not in {
                        "id",
                        "created_at",
                        "updated_at",
                        "idempotency_key",  # Block idempotency_key updates to preserve deduplication
                    }
                    and value is not None
                ):  # Ignore None values to avoid constraint violations
                    setattr(db_catering_request, key, value)

            self.session.commit()
            self.session.refresh(db_catering_request)
            return db_catering_request
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error updating catering request: {e}")
            raise
        except Exception as e:
            self.session.rollback()
            logger.exception(
                f"Unexpected error while updating catering request {catering_request_id}: {e}"
            )
            raise
