"""Routine Repository.

Provides async database operations for routines and routine items.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.routine_items import RoutineItem
from db.tables.routines import Routine
from db.tables.types import RoutineCategory, RoutineInputType
from utils.log import logger


class RoutineRepositoryAsync:
    """Async repository for routine and routine item operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========================================================================
    # Routine CRUD
    # ========================================================================

    async def create_routine(
        self,
        project_id: uuid.UUID,
        name: str,
        description: str | None = None,
        category: RoutineCategory = RoutineCategory.custom,
        is_active: bool = True,
    ) -> Routine:
        """
        Create a new routine in the database.

        Args:
            project_id: Project ID to associate the routine with
            name: Name of the routine
            description: Optional description
            category: Category of the routine
            is_active: Whether the routine is active

        Returns:
            The created Routine object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            routine = Routine(
                project_id=project_id,
                name=name,
                description=description,
                category=category,
                is_active=is_active,
            )
            self.session.add(routine)
            await self.session.flush()
            await self.session.refresh(routine)
            return routine
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating routine: {e}")
            raise

    async def get_routine_by_id(self, routine_id: uuid.UUID) -> Routine | None:
        """
        Retrieve a routine by its ID.

        Args:
            routine_id: UUID of the routine

        Returns:
            Routine object if found, None otherwise
        """
        try:
            stmt = select(Routine).where(Routine.id == routine_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting routine by id: {e}")
            return None

    async def list_routines_by_project(
        self,
        project_id: uuid.UUID,
        is_active: bool | None = None,
    ) -> list[Routine]:
        """
        List all routines for a specific project.

        Args:
            project_id: UUID of the project
            is_active: Optional filter for active status

        Returns:
            List of Routine objects
        """
        try:
            stmt = select(Routine).where(Routine.project_id == project_id)

            if is_active is not None:
                stmt = stmt.where(Routine.is_active == is_active)

            stmt = stmt.order_by(Routine.created_at.desc())
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing routines by project: {e}")
            return []

    async def update_routine(
        self,
        routine_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        category: RoutineCategory | None = None,
        is_active: bool | None = None,
    ) -> Routine | None:
        """
        Update a routine by its ID.

        Args:
            routine_id: UUID of the routine
            name: Optional new name
            description: Optional new description
            category: Optional new category
            is_active: Optional new active status

        Returns:
            Updated Routine object if found, None otherwise
        """
        try:
            routine = await self.get_routine_by_id(routine_id)
            if not routine:
                return None

            if name is not None:
                routine.name = name
            if description is not None:
                routine.description = description
            if category is not None:
                routine.category = category
            if is_active is not None:
                routine.is_active = is_active

            await self.session.flush()
            await self.session.refresh(routine)
            return routine
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating routine: {e}")
            return None

    async def delete_routine(self, routine_id: uuid.UUID) -> bool:
        """
        Delete a routine by its ID.

        This will also delete associated items due to application-level cascade.

        Args:
            routine_id: UUID of the routine

        Returns:
            True if deleted, False if not found
        """
        try:
            routine = await self.get_routine_by_id(routine_id)
            if not routine:
                return False

            # Delete associated items first
            items = await self.list_items_by_routine(routine_id)
            for item in items:
                await self.session.delete(item)

            await self.session.delete(routine)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting routine: {e}")
            return False

    # ========================================================================
    # RoutineItem CRUD
    # ========================================================================

    async def create_routine_item(
        self,
        routine_id: uuid.UUID,
        name: str,
        description: str | None = None,
        sort_order: int = 0,
        input_type: RoutineInputType = RoutineInputType.photo,
        is_required: bool = True,
        reference_image_url: str | None = None,
        ai_rules: dict[str, Any] | None = None,
        signal_source_id: uuid.UUID | None = None,
    ) -> RoutineItem:
        """
        Create a new routine item in the database.

        Args:
            routine_id: Parent routine ID
            name: Name of the item
            description: Optional description
            sort_order: Order in the routine
            input_type: Type of input (V1: photo only)
            is_required: Whether the item is required
            reference_image_url: Optional S3 URL for reference image
            ai_rules: Optional AI verification rules
            signal_source_id: Optional camera integration

        Returns:
            The created RoutineItem object

        Raises:
            SQLAlchemyError: If there is a database error
        """
        try:
            item = RoutineItem(
                routine_id=routine_id,
                name=name,
                description=description,
                sort_order=sort_order,
                input_type=input_type,
                is_required=is_required,
                reference_image_url=reference_image_url,
                ai_rules=ai_rules or {},
                signal_source_id=signal_source_id,
            )
            self.session.add(item)
            await self.session.flush()
            await self.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating routine item: {e}")
            raise

    async def get_routine_item_by_id(self, item_id: uuid.UUID) -> RoutineItem | None:
        """
        Retrieve a routine item by its ID.

        Args:
            item_id: UUID of the routine item

        Returns:
            RoutineItem object if found, None otherwise
        """
        try:
            stmt = select(RoutineItem).where(RoutineItem.id == item_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error getting routine item by id: {e}")
            return None

    async def list_items_by_routine(
        self,
        routine_id: uuid.UUID,
    ) -> list[RoutineItem]:
        """
        List all items for a specific routine, ordered by sort_order.

        Args:
            routine_id: UUID of the routine

        Returns:
            List of RoutineItem objects
        """
        try:
            stmt = (
                select(RoutineItem)
                .where(RoutineItem.routine_id == routine_id)
                .order_by(RoutineItem.sort_order)
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error listing items by routine: {e}")
            return []

    async def update_routine_item(
        self,
        item_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
        input_type: RoutineInputType | None = None,
        is_required: bool | None = None,
        reference_image_url: str | None = None,
        ai_rules: dict[str, Any] | None = None,
        signal_source_id: uuid.UUID | None = None,
    ) -> RoutineItem | None:
        """
        Update a routine item by its ID.

        Args:
            item_id: UUID of the routine item
            name: Optional new name
            description: Optional new description
            sort_order: Optional new sort order
            input_type: Optional new input type
            is_required: Optional new required status
            reference_image_url: Optional new reference image URL
            ai_rules: Optional new AI rules
            signal_source_id: Optional new signal source ID

        Returns:
            Updated RoutineItem object if found, None otherwise
        """
        try:
            item = await self.get_routine_item_by_id(item_id)
            if not item:
                return None

            if name is not None:
                item.name = name
            if description is not None:
                item.description = description
            if sort_order is not None:
                item.sort_order = sort_order
            if input_type is not None:
                item.input_type = input_type
            if is_required is not None:
                item.is_required = is_required
            if reference_image_url is not None:
                item.reference_image_url = reference_image_url
            if ai_rules is not None:
                item.ai_rules = ai_rules
            if signal_source_id is not None:
                item.signal_source_id = signal_source_id

            await self.session.flush()
            await self.session.refresh(item)
            return item
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating routine item: {e}")
            return None

    async def delete_routine_item(self, item_id: uuid.UUID) -> bool:
        """
        Delete a routine item by its ID.

        Args:
            item_id: UUID of the routine item

        Returns:
            True if deleted, False if not found
        """
        try:
            item = await self.get_routine_item_by_id(item_id)
            if not item:
                return False

            await self.session.delete(item)
            await self.session.flush()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting routine item: {e}")
            return False

    async def get_next_sort_order(self, routine_id: uuid.UUID) -> int:
        """
        Get the next available sort order for a routine's items.

        Args:
            routine_id: UUID of the routine

        Returns:
            Next available sort order (max + 1, or 0 if no items)
        """
        items = await self.list_items_by_routine(routine_id)
        if not items:
            return 0
        return max(item.sort_order for item in items) + 1
