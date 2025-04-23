import uuid
from typing import Any, Dict, List

from ddtrace import tracer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session, selectinload

from db.tables import Project
from utils.log import logger


class ProjectRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    @tracer.wrap()
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
        # ISSUE: this query is called for each request.
        query = (
            select(Project)
            .options(selectinload(Project.account))
            .filter(Project.channel_identifiers.contains([channel_identifier]))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    @tracer.wrap()
    async def get_project(self, id: uuid.UUID) -> Project | None:
        """
        Retrieve a project by its ID asynchronously.
        Args:
            id (uuid.UUID): The ID of the project.
        Returns:
            Project, or None if no such Project is found.
        """
        query = (
            select(Project)
            .options(selectinload(Project.account))
            .filter(Project.id == id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class ProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    @tracer.wrap()
    def create_project(
        self, account_id: uuid.UUID, project_name: str, **kwargs
    ) -> Project:
        """
        Create a new project.
        Args:
            account_id (uuid.UUID): The account ID associated with the project.
            project_name (str): The name of the project.
            **kwargs: Additional project attributes.
        Returns:
            The newly created Project.
        """
        project = Project(account_id=account_id, name=project_name, **kwargs)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    @tracer.wrap()
    def update_project(self, project_id: uuid.UUID, **kwargs) -> Project | None:
        """
        Update a project.
        Args:
            project_id (uuid.UUID): The ID of the project to update.
            **kwargs: The attributes to update.
        Returns:
            The updated Project, or None if no such Project is found.
        """
        project = self.get_project(project_id)
        if project:
            for key, value in kwargs.items():
                setattr(project, key, value)
            self.session.commit()
            self.session.refresh(project)
        return project

    @tracer.wrap()
    def get_project(self, project_id: uuid.UUID) -> Project | None:
        return self.session.query(Project).filter(Project.id == project_id).first()

    @tracer.wrap()
    def get_project_by_name(self, project_name: str) -> Project | None:
        return self.session.query(Project).filter(Project.name == project_name).first()

    @tracer.wrap()
    def get_project_by_channel(self, channel_platform: str, channel_identifier: str):
        """
        Retrieve a project by channel platform and identifier.
        Args:
            channel_platform (str): The platform of the channel (e.g., 'sms', 'voice').
            channel_identifier (str): The identifier of the channel (e.g., phone number).
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
            self.session.query(Project)
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

    @tracer.wrap()
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
            self.session.query(Project)
            .filter(Project.channel_identifiers.contains([channel_identifier]))
            .first()
        )
        return project

    @tracer.wrap()
    def update_project_config(self, project_id: uuid.UUID, config: Dict[str, Any]):
        """
        Update a project's configuration.
        Args:
            project_id (uuid.UUID): The ID of the project to update.
            config (Dict[str, Any]): The configuration to update.
        """
        try:
            project = self.get_project(project_id)
            if project is None:
                raise ValueError(f"Project {project_id} not found")

            project.raw_config.update(config)
            self.session.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error updating project config: {e}")
            raise

    @tracer.wrap()
    def replace_project_channel_identifiers(
        self, project_id: uuid.UUID, channel_identifiers: List[str]
    ) -> None:
        """
        Replace a project's channel identifiers.
        Args:
            project_id (uuid.UUID): The ID of the project to update.
            channel_identifiers (List[str]): The new channel identifiers.
        """
        try:
            project = self.get_project(project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")

            project.channel_identifiers = channel_identifiers
            self.session.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error replacing project channel identifiers: {e}")
            raise

    @tracer.wrap()
    def replace_project_config(
        self, project_id: uuid.UUID, config: Dict[str, Any]
    ) -> None:
        """
        Replace a project's configuration.
        Args:
            project_id (uuid.UUID): The ID of the project to update.
            config (Dict[str, Any]): The new configuration.
        """
        try:
            project = self.get_project(project_id)
            if project is None:
                raise ValueError(f"project {project_id} not found")

            project.raw_config = config
            self.session.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error replacing project config: {e}")
            raise

    @tracer.wrap()
    def delete_project(self, project_id: uuid.UUID) -> None:
        """
        Delete a project.
        Args:
            project_id (uuid.UUID): The ID of the project to delete.
        """
        try:
            project = self.get_project(project_id)
            if project:
                self.session.delete(project)
                self.session.commit()
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error deleting project: {e}")
            raise
