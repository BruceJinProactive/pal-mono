import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from db.tables import Project
from utils.log import logger


def _format_time(time_str: str) -> str:
    """Convert Google Places time format to 12-hour format.

    Args:
        time_str: Time in HHMM format (e.g., "1200", "0900")

    Returns:
        Time in 12-hour format (e.g., "12:00 PM", "9:00 AM")
    """
    if not time_str or len(time_str) != 4 or not time_str.isdigit():
        return time_str

    hour = int(time_str[:2])
    minute_int = int(time_str[2:])

    # Handle "2400" as midnight (end of day), used by Google Places API
    if hour == 24 and minute_int == 0:
        return "12:00 AM"

    # Validate hour/minute ranges
    if hour > 23 or minute_int > 59:
        return time_str

    minute = time_str[2:]
    period = "AM" if hour < 12 else "PM"

    if hour == 0:
        hour = 12
    elif hour > 12:
        hour -= 12

    return f"{hour}:{minute} {period}"


def _format_special_hours(special_hours: list) -> list[str]:
    """Format special hours (holidays, exceptional days) for display.

    Args:
        special_hours: List of special hour entries, each with:
            - date: Date string in YYYY-MM-DD format
            - exceptional_hours: Boolean flag
            - periods: List of open/close times (empty = closed)

    Returns:
        List of formatted strings like "Thursday, Dec 25: 12:00 PM – 4:00 PM (Holiday Hours)"
    """
    formatted = []

    for entry in special_hours:
        date_str = entry.get("date")
        if not date_str:
            continue

        # Parse date and format as "Thursday, Dec 25"
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %b %d").replace(" 0", " ")
        except ValueError:
            formatted_date = date_str

        periods = entry.get("periods", [])

        if not periods:
            # No periods means closed
            formatted.append(f"{formatted_date}: Closed (Holiday Hours)")
        else:
            # Format the time range from first period
            period = periods[0]
            open_time = period.get("open", {}).get("time", "")
            close_time = period.get("close", {}).get("time", "")

            if open_time and close_time:
                formatted_open = _format_time(open_time)
                formatted_close = _format_time(close_time)
                formatted.append(
                    f"{formatted_date}: {formatted_open} – {formatted_close} (Holiday Hours)"
                )
            elif open_time:
                formatted_open = _format_time(open_time)
                formatted.append(
                    f"{formatted_date}: Opens {formatted_open} (Holiday Hours)"
                )
            elif close_time:
                formatted_close = _format_time(close_time)
                formatted.append(
                    f"{formatted_date}: Closes {formatted_close} (Holiday Hours)"
                )

    return formatted


class ProjectRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

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
        project = result.scalar_one_or_none()
        return project

    async def get_project(self, id: uuid.UUID) -> Project | None:
        """
        Retrieve a project by its ID asynchronously.
        Args:
            id (uuid.UUID): The unique identifier of the project.
        Returns:
            Project, or None if no such Project is found.
        """
        query = (
            select(Project)
            .options(selectinload(Project.account))
            .filter(Project.id == id)
        )
        result = await self.session.execute(query)
        project = result.scalar_one_or_none()
        return project

    async def create_project(
        self, account_id: uuid.UUID, project_name: str, **kwargs
    ) -> Project:
        """
        Create a new project asynchronously.

        Args:
            account_id (uuid.UUID): The unique identifier of the account.
            project_name (str): The name of the project.
            **kwargs: Additional project attributes.

        Returns:
            Project: The created project.

        Raises:
            ValueError: If there is a validation error.
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            db_project = Project(account_id=account_id, name=project_name)
            for key, value in kwargs.items():
                if value is not None and hasattr(db_project, key):
                    setattr(db_project, key, value)

            self.session.add(db_project)
            await self.session.commit()
            await self.session.refresh(db_project)
            return db_project
        except IntegrityError as e:
            await self.session.rollback()
            logger.error(f"Error creating project: {e}")
            error_summary = str(e).split("\n")[0]
            raise ValueError(f"Error creating project: {error_summary}")
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating project: {e}")
            raise

    async def delete_project(self, project_id: uuid.UUID) -> None:
        """
        Delete a project from the database asynchronously.

        Args:
            project_id (uuid.UUID): The unique identifier of the project.

        Raises:
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            project = await self.get_project(project_id)
            if project:
                await self.session.delete(project)
                await self.session.commit()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting project: {e}")
            raise


class ProjectRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_project(
        self, account_id: uuid.UUID, project_name: str, **kwargs
    ) -> Project:
        try:
            db_project = Project(account_id=account_id, name=project_name)
            for key, value in kwargs.items():
                if value is not None and hasattr(db_project, key):
                    setattr(db_project, key, value)
            self.session.add(db_project)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_project)
            return db_project
        except IntegrityError as e:
            self.session.rollback()
            logger.error(f"Error creating project: {e}")
            error_summary = str(e).split("\n")[0]
            raise ValueError(f"Error creating project: {error_summary}")
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating project: {e}")
            raise

    def update_project(
        self, project_id: uuid.UUID, expected_version: int | None = None, **kwargs
    ) -> Project | None:
        try:
            db_project = (
                self.session.query(Project).filter(Project.id == project_id).first()
            )
            if not db_project:
                return None

            if expected_version is not None and db_project.updated_at:
                if int(db_project.updated_at.timestamp()) != expected_version:
                    raise ValueError(
                        f"Version mismatch: Project {project_id} has been modified since last retrieval."
                    )

            for key, value in kwargs.items():
                # Skip None values to avoid accidentally clearing fields
                if value is not None and hasattr(db_project, key):
                    setattr(db_project, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(db_project)
            return db_project
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating project: {e}")
            raise

    def get_project(self, project_id: uuid.UUID) -> Project | None:
        return self.session.query(Project).filter(Project.id == project_id).first()

    def get_project_by_name(self, project_name: str) -> Project | None:
        return self.session.query(Project).filter(Project.name == project_name).first()

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

    def get_projects_by_phone_number(self, phone_number: str) -> List[Project]:
        """
        Find all projects associated with a phone number by checking different channel prefixes.

        Args:
            phone_number (str): The phone number to search for (e.g., "+15551234567").

        Returns:
            List of Projects associated with the phone number. Empty list if none found.
        """
        # Query all projects that have this phone number in any channel identifier
        # Using SQL for efficiency since we need to check multiple prefixes
        # Use TRIM to handle trailing spaces in stored phone numbers
        projects = (
            self.session.query(Project)
            .filter(
                text(
                    """
                EXISTS (
                    SELECT 1 FROM unnest(channel_identifiers) AS channel_id
                    WHERE TRIM(channel_id) LIKE :voice_pattern
                       OR TRIM(channel_id) LIKE :sms_pattern
                       OR TRIM(channel_id) LIKE :phone_pattern
                )
                """
                )
            )
            .params(
                voice_pattern=f"voice:{phone_number}",
                sms_pattern=f"sms:{phone_number}",
                phone_pattern=f"phone:{phone_number}",
            )
            .all()
        )

        return projects

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

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
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

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
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

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error replacing project config: {e}")
            raise

    def delete_project(self, project_id: uuid.UUID) -> None:
        """
        Delete a project from the database.

        Args:
            project_id (uuid.UUID): The unique identifier of the project.

        Raises:
            SQLAlchemyError: If there is an error committing the transaction to the database.
        """
        try:
            project = self.get_project(project_id)
            if project:
                self.session.delete(project)
                if self.auto_commit:
                    self.session.commit()
                else:
                    self.session.flush()
        except (SQLAlchemyError, ValueError) as e:
            self.session.rollback()
            logger.error(f"Error deleting project: {e}")
            raise

    def get_projects_by_account_id(self, account_id: uuid.UUID) -> List[Project]:
        """
        Retrieve all projects belonging to a specific account.

        Args:
            account_id (uuid.UUID): The unique identifier of the account.

        Returns:
            List[Project]: A list of projects belonging to the account, sorted by created_at in ascending order.
        """
        projects = (
            self.session.query(Project)
            .filter(Project.account_id == account_id)
            .order_by(Project.created_at)
            .all()
        )
        return projects

    def get_projects_by_ids(self, project_ids: List[uuid.UUID]) -> List[Project]:
        """
        Retrieve projects by a list of project IDs.

        Args:
            project_ids (List[uuid.UUID]): List of project IDs to fetch.

        Returns:
            List[Project]: A list of projects matching the provided IDs.
        """
        if not project_ids:
            return []

        try:
            projects = (
                self.session.query(Project).filter(Project.id.in_(project_ids)).all()
            )
            return projects
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving projects by IDs: {e}")
            return []

    def get_projects_with_google_place_id(self) -> List[Project]:
        """
        Get all projects (stores) that have a google_place_id configured.

        Returns:
            List[Project]: Projects with valid Google Place IDs.
        """
        try:
            projects = (
                self.session.query(Project)
                .options(selectinload(Project.account))
                .filter(
                    Project.google_place_id.isnot(None), Project.google_place_id != ""
                )
                .all()
            )
            return projects
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving projects with google_place_id: {e}")
            return []

    def get_projects_needing_hours_update(
        self, hours_threshold: int = 24
    ) -> List[Project]:
        """
        Get projects whose hours haven't been updated recently.

        Args:
            hours_threshold: Hours since last update (default: 24)

        Returns:
            List[Project]: Projects that need hours updates.
        """
        try:
            threshold_time = datetime.now(timezone.utc) - timedelta(
                hours=hours_threshold
            )

            projects = (
                self.session.query(Project)
                .options(selectinload(Project.account))
                .filter(
                    Project.google_place_id.isnot(None),
                    Project.google_place_id != "",
                    or_(
                        Project.business_hours_last_updated.is_(None),
                        Project.business_hours_last_updated < threshold_time,
                    ),
                )
                .all()
            )
            return projects
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving projects needing hours update: {e}")
            return []

    def update_project_business_hours(
        self,
        project_id: uuid.UUID,
        business_hours: Dict[str, Any],
        last_updated: Any,
    ) -> Project:
        """
        Update business hours for a project (store location).

        Args:
            project_id: The project ID to update
            business_hours: Structured hours data from Google Places API
            last_updated: Timestamp of the update

        Returns:
            Project: The updated project

        Raises:
            ValueError: If project not found
            SQLAlchemyError: If database error occurs
        """
        try:
            project = self.get_project(project_id)
            if not project:
                raise ValueError(f"Project {project_id} not found")

            project.business_hours = business_hours
            project.business_hours_last_updated = last_updated
            project.updated_at = datetime.now(timezone.utc)

            # Also update the human-readable store_hours field
            regular_hours = business_hours.get("regular_hours") or {}
            weekday_text = regular_hours.get("weekday_text", [])
            store_hours_parts = []

            if weekday_text:
                store_hours_parts.append("\n".join(weekday_text))

            # Append special hours (holidays, exceptional days)
            special_hours = business_hours.get("special_hours") or []
            if special_hours:
                formatted_special = _format_special_hours(special_hours)
                if formatted_special:
                    store_hours_parts.append(
                        "Special Hours:\n" + "\n".join(formatted_special)
                    )

            if store_hours_parts:
                project.store_hours = "\n\n".join(store_hours_parts)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(project)
            return project
        except ValueError:
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating project business hours: {e}")
            raise

    def get_projects_with_coupons(self) -> List[Project]:
        """Retrieve all projects that have a Stripe coupon assigned."""
        try:
            return (
                self.session.query(Project)
                .filter(Project.stripe_coupon_id.isnot(None))
                .all()
            )
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error retrieving projects with coupons: {e}")
            return []
