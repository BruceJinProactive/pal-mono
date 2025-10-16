import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import CateringRequest
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
            CateringRequest: The created catering request with generated ID and timestamps.
        """
        db_catering_request = CateringRequest()
        for key, value in vars(catering_request).items():
            if hasattr(CateringRequest, key) and key not in {
                "id",
                "created_at",
                "updated_at",
            }:
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
                if hasattr(CateringRequest, key) and key not in {
                    "id",
                    "created_at",
                    "updated_at",
                }:
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
        Create a new catering request synchronously.
        Args:
            catering_request (CateringRequest): The catering request object to create.
        Returns:
            CateringRequest: The created catering request with generated ID and timestamps.
        """
        db_catering_request = CateringRequest()
        for key, value in vars(catering_request).items():
            if hasattr(CateringRequest, key) and key not in {
                "id",
                "created_at",
                "updated_at",
            }:
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
