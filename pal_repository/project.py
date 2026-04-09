from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.projects import Project
from pal_repository.data_classes.project import ProjectData
from utils.log import logger


def _to_data(row: Project) -> ProjectData:
    """Convert an ORM Project to a ProjectData."""
    return ProjectData(
        id=row.id,
        name=row.name,
        account_id=row.account_id,
        agent_id=row.agent_id,
        display_name=row.display_name,
        raw_config=dict(row.raw_config) if row.raw_config else {},
        channel_identifiers=(
            list(row.channel_identifiers) if row.channel_identifiers else []
        ),
        store_hours=row.store_hours,
        address=row.address,
        product_info=row.product_info,
        service_instruction=row.service_instruction,
        order_integration_id=row.order_integration_id,
        timezone=row.timezone,
        transfer_message=row.transfer_message,
        transfer_phone_number=row.transfer_phone_number,
        show_agent_caller_id=row.show_agent_caller_id,
        reservation_link=row.reservation_link,
        ordering_link=row.ordering_link,
        call_forwarding_setup_completed=row.call_forwarding_setup_completed,
        stripe_customer_id=row.stripe_customer_id,
        stripe_coupon_id=row.stripe_coupon_id,
        current_subscription_id=row.current_subscription_id,
        google_place_id=row.google_place_id,
        business_hours=(
            dict(row.business_hours) if row.business_hours is not None else None
        ),
        business_hours_last_updated=row.business_hours_last_updated,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProjectRepository:
    """Async-only repository for Project records.

    All methods return ``ProjectData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, project_id: uuid.UUID) -> ProjectData | None:
        """Retrieve a single project by its primary key."""
        try:
            result = await self.session.execute(
                select(Project).filter(Project.id == project_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project by ID: {e}")
            raise

    async def get_by_name(self, name: str) -> ProjectData | None:
        """Retrieve a single project by its unique name."""
        try:
            result = await self.session.execute(
                select(Project).filter(Project.name == name)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project by name: {e}")
            raise

    async def list_by_account_id(self, account_id: uuid.UUID) -> list[ProjectData]:
        """List all projects belonging to a given account."""
        try:
            result = await self.session.execute(
                select(Project)
                .filter(Project.account_id == account_id)
                .order_by(Project.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error listing projects by account ID: {e}")
            raise

    async def list_by_ids(self, project_ids: list[uuid.UUID]) -> list[ProjectData]:
        """Retrieve multiple projects by their IDs."""
        if not project_ids:
            return []
        try:
            result = await self.session.execute(
                select(Project).filter(Project.id.in_(project_ids))
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"Error listing projects by IDs: {e}")
            raise

    async def get_by_channel_identifier(
        self, channel_identifier: str
    ) -> ProjectData | None:
        """Retrieve a project by a channel identifier.

        Uses ``scalars().first()`` because channel identifiers are not
        enforced-unique across projects at the DB level.
        """
        try:
            result = await self.session.execute(
                select(Project).filter(
                    Project.channel_identifiers.contains([channel_identifier])
                )
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving project by channel identifier: {e}")
            raise

    async def create(self, record: ProjectData) -> None:
        """Create a new project.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        try:
            row = Project(
                id=uuid.uuid4(),
                name=record.name,
                account_id=record.account_id,
                agent_id=record.agent_id,
                display_name=record.display_name,
                raw_config=record.raw_config or {},
                channel_identifiers=record.channel_identifiers or [],
                store_hours=record.store_hours,
                address=record.address,
                product_info=record.product_info,
                service_instruction=record.service_instruction,
                order_integration_id=record.order_integration_id,
                timezone=record.timezone,
                transfer_message=record.transfer_message,
                transfer_phone_number=record.transfer_phone_number,
                show_agent_caller_id=(
                    record.show_agent_caller_id
                    if record.show_agent_caller_id is not None
                    else False
                ),
                reservation_link=record.reservation_link,
                ordering_link=record.ordering_link,
                call_forwarding_setup_completed=(
                    record.call_forwarding_setup_completed
                    if record.call_forwarding_setup_completed is not None
                    else False
                ),
                stripe_customer_id=record.stripe_customer_id,
                stripe_coupon_id=record.stripe_coupon_id,
                current_subscription_id=record.current_subscription_id,
                google_place_id=record.google_place_id,
                business_hours=record.business_hours,
                business_hours_last_updated=record.business_hours_last_updated,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating project: {e}")
            raise

    async def update(
        self,
        project_id: uuid.UUID,
        record: ProjectData,
    ) -> None:
        """Update an existing project.

        Fields from *record* that are non-None overwrite the existing values.

        Note: required fields (``name``) and fields with ``default_factory``
        (``raw_config``, ``channel_identifiers``) are never None, so they are
        always written.  Callers must populate these with the current values
        when they only intend to patch a subset of fields.
        """
        try:
            result = await self.session.execute(
                select(Project).filter(Project.id == project_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            if record.name is not None:
                row.name = record.name
            if record.display_name is not None:
                row.display_name = record.display_name
            if record.raw_config is not None:
                row.raw_config = record.raw_config
            if record.channel_identifiers is not None:
                row.channel_identifiers = record.channel_identifiers
            if record.store_hours is not None:
                row.store_hours = record.store_hours
            if record.address is not None:
                row.address = record.address
            if record.product_info is not None:
                row.product_info = record.product_info
            if record.service_instruction is not None:
                row.service_instruction = record.service_instruction
            if record.order_integration_id is not None:
                row.order_integration_id = record.order_integration_id
            if record.timezone is not None:
                row.timezone = record.timezone
            if record.transfer_message is not None:
                row.transfer_message = record.transfer_message
            if record.transfer_phone_number is not None:
                row.transfer_phone_number = record.transfer_phone_number
            if record.reservation_link is not None:
                row.reservation_link = record.reservation_link
            if record.ordering_link is not None:
                row.ordering_link = record.ordering_link
            if record.stripe_customer_id is not None:
                row.stripe_customer_id = record.stripe_customer_id
            if record.stripe_coupon_id is not None:
                row.stripe_coupon_id = record.stripe_coupon_id
            if record.current_subscription_id is not None:
                row.current_subscription_id = record.current_subscription_id
            if record.google_place_id is not None:
                row.google_place_id = record.google_place_id
            if record.business_hours is not None:
                row.business_hours = record.business_hours
            if record.business_hours_last_updated is not None:
                row.business_hours_last_updated = record.business_hours_last_updated

            if record.show_agent_caller_id is not None:
                row.show_agent_caller_id = record.show_agent_caller_id
            if record.call_forwarding_setup_completed is not None:
                row.call_forwarding_setup_completed = (
                    record.call_forwarding_setup_completed
                )

            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating project: {e}")
            raise

    async def delete(self, project_id: uuid.UUID) -> ProjectData | None:
        """Delete a project by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(Project).filter(Project.id == project_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting project: {e}")
            raise
