from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.catering_menu import CateringMenuData
from db.pal_repository.data_classes.routine_execution import UNSET, _Unset
from db.tables.catering_menus import CateringMenu
from utils.log import logger


def _to_data(row: CateringMenu) -> CateringMenuData:
    return CateringMenuData(
        id=row.id,
        project_id=row.project_id,
        account_id=row.account_id,
        item_name=row.item_name,
        item_price=row.item_price,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CateringMenuRepository:
    """Async-only repository for catering menu items."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_project_id(
        self,
        project_id: uuid.UUID,
    ) -> list[CateringMenuData]:
        """Retrieve all catering menu items for a project."""
        try:
            result = await self.session.execute(
                select(CateringMenu)
                .filter(CateringMenu.project_id == project_id)
                .order_by(CateringMenu.item_name.asc())
            )
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving catering menu items by project")
            raise

    async def list_by_account_and_project_ids(
        self,
        account_id: uuid.UUID,
        project_ids: list[uuid.UUID],
    ) -> list[CateringMenu]:
        """Retrieve catering menu ORM rows for an account across projects."""
        if not project_ids:
            return []

        try:
            result = await self.session.execute(
                select(CateringMenu)
                .filter(CateringMenu.account_id == account_id)
                .filter(CateringMenu.project_id.in_(project_ids))
            )
            return list(result.scalars().all())
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving catering menu items by account")
            raise

    def add(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID,
        item_name: str,
        item_price: Decimal,
    ) -> CateringMenu:
        """Stage a new catering menu item for insertion."""
        row = CateringMenu(
            account_id=account_id,
            project_id=project_id,
            item_name=item_name,
            item_price=item_price,
        )
        self.session.add(row)
        return row

    async def update(
        self,
        menu_item_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        item_name: str | _Unset = UNSET,
        item_price: Decimal | _Unset = UNSET,
    ) -> CateringMenuData | None:
        """Update a catering menu item by ID."""
        try:
            query = select(CateringMenu).filter(CateringMenu.id == menu_item_id)
            if project_id is not None:
                query = query.filter(CateringMenu.project_id == project_id)
            result = await self.session.execute(query)
            row = result.scalar_one_or_none()
            if row is None:
                return None

            if not isinstance(item_name, _Unset):
                row.item_name = item_name
            if not isinstance(item_price, _Unset):
                row.item_price = item_price

            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error updating catering menu item")
            raise
