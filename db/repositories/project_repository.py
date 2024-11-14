import uuid
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from db.tables import Project
from utils.log import logger


class ProjectRepositoryAsync:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_project_by_channel_identifier(
        self, channel_identifier: str
    ) -> Project | None:
        """
        Retrieve a project by a channel identifier asynchronously.
        Args:
            channel_identifier (str): The identifier of the channel (e.g., phone number).
        Returns:
            Project, or None if no such Project is found.
        """
        # Use the `contains` operator for fast lookup
        query = select(Project).filter(
            Project.channel_identifiers.contains([channel_identifier])
        )
        result = await self.db.execute(query)
        project = result.scalar_one_or_none()
        return project


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_project(
        self, project_name: str, account_id: uuid.UUID, agent_id: uuid.UUID
    ) -> Project:
        db_project = Project(
            name=project_name, account_id=account_id, agent_id=agent_id
        )
        self.db.add(db_project)
        self.db.commit()
        return db_project

    def get_project(self, project_id: uuid.UUID) -> Project | None:
        return self.db.query(Project).filter(Project.id == project_id).first()

    def get_project_by_channel(self, channel_platform: str, channel_identifier: str):
        """
        Retrieve a project by the channel platform and identifiers.

        Args:
            channel_platform (str): The platform of the channel (eg. sms, whatsapp).
            channel_identifier (str): The identifier of the channel (eg. phone number).

        Returns:
            Project, or None if no such Project is found.
        """

        if not channel_platform:
            raise ValueError("'channel_platform' must be provided")
        if not channel_identifier:
            raise ValueError("'channel_identifier' must be provided")

        channel_filter = f'{{"platform": "{channel_platform}", "identifier": "{channel_identifier}"}}'

        """
        The query should return the project that contains the channel_platform and channel_identifier pair in
        raw_config[channels].

        We use jsonb_array_elements to search over all elements in raw_config->'channels', and use
        @> to match the pair.
        """
        query = (
            self.db.query(Project)
            .filter(
                text(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements(raw_config->'channels') AS elem "
                    "WHERE elem @> :channel_filter)"
                )
            )
            .params(channel_filter=channel_filter)
        )

        project = query.first()
        return project

    def get_project_by_channel_identifier(
        self, channel_identifier: str
    ) -> Project | None:
        """
        Retrieve a project by a channel identifier.

        Args:
            channel_identifier (str): The identifier of the channel (e.g., phone number).

        Returns:
            Project, or None if no such Project is found.
        """
        # Use the `contains` operator for fast lookup
        project = (
            self.db.query(Project)
            .filter(Project.channel_identifiers.contains([channel_identifier]))
            .first()
        )
        return project

    def update_project_config(self, project_id: uuid.UUID, config: Dict[str, Any]):
        """Update a project's config in the database.

        This function is best used to update specific fields in the configuration object.

        Args:
            project_id (uuid.UUID): The unique identifier of the project.
            config (Dict[str, Any]): The configuration dictionary to update the project's config with.

        Raises:
            ValueError: If the project with the given ID is not found.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            project = self.get_project(project_id)
            if project is None:
                raise ValueError(f"Project {project_id} not found")

            project.raw_config.update(config)
            self.db.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error updating project config: {e}")
            raise

    def replace_project_channel_identifiers(
        self, project_id: uuid.UUID, channel_identifiers: List[str]
    ) -> None:
        """Replace an project's channel identifiers in the database.

        This function replaces the entire `channel_identifiers` for the specified project.

        Args:
            project_id (uuid.UUID): The unique identifier of the project.
            channel_identifiers (List[str]): The new `channel_identifiers` to replace the existing one.

        Raises:
            ValueError: If the project with the given ID is not found.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            project = self.get_project(project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")

            project.channel_identifiers = channel_identifiers
            self.db.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error replacing project channel identifiers: {e}")
            raise

    def replace_project_config(
        self, project_id: uuid.UUID, config: Dict[str, Any]
    ) -> None:
        """Replace an project's config in the database.

        This function replaces the entire `raw_config` for the specified project.

        Args:
            project_id (uuid.UUID): The unique identifier of the project.
            config (Dict[str, Any]): The new `raw_config` to replace the existing one.

        Raises:
            ValueError: If the project with the given ID is not found.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            project = self.get_project(project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")

            project.raw_config = config
            self.db.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.db.rollback()
            logger.error(f"Error replacing project config: {e}")
            raise
