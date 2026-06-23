import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.catering_menu import CateringMenuRepository
from db.pal_repository.data_classes.catering_menu import CateringMenuData
from db.tables.catering_menus import CateringMenu


def _make_menu_row() -> MagicMock:
    row = MagicMock(spec=CateringMenu)
    row.id = uuid.uuid4()
    row.project_id = uuid.uuid4()
    row.account_id = uuid.uuid4()
    row.item_name = "Sandwich platter"
    row.item_price = Decimal("145.50")
    row.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return row


@pytest.mark.asyncio
async def test_list_by_project_id_returns_menu_data() -> None:
    session = AsyncMock()
    repo = CateringMenuRepository(session)
    row = _make_menu_row()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [row]
    result.scalars.return_value = scalars
    session.execute.return_value = result

    items = await repo.list_by_project_id(row.project_id)

    assert len(items) == 1
    assert isinstance(items[0], CateringMenuData)
    assert items[0].id == row.id
    assert items[0].item_name == "Sandwich platter"
    assert items[0].item_price == Decimal("145.50")


@pytest.mark.asyncio
async def test_list_by_project_id_raises_db_errors() -> None:
    session = AsyncMock()
    repo = CateringMenuRepository(session)
    session.execute.side_effect = RuntimeError("db offline")

    with pytest.raises(RuntimeError, match="db offline"):
        await repo.list_by_project_id(uuid.uuid4())

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_returns_none_when_missing() -> None:
    session = AsyncMock()
    repo = CateringMenuRepository(session)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    updated = await repo.update(uuid.uuid4(), item_name="Missing platter")

    assert updated is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_persists_provided_fields() -> None:
    session = AsyncMock()
    repo = CateringMenuRepository(session)
    row = _make_menu_row()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result

    updated = await repo.update(
        row.id,
        project_id=row.project_id,
        item_name="Updated platter",
        item_price=Decimal("155.00"),
    )

    assert updated is not None
    assert updated.item_name == "Updated platter"
    assert updated.item_price == Decimal("155.00")
    assert row.item_name == "Updated platter"
    assert row.item_price == Decimal("155.00")
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(row)


@pytest.mark.asyncio
async def test_update_rolls_back_on_error() -> None:
    session = AsyncMock()
    repo = CateringMenuRepository(session)
    row = _make_menu_row()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result
    session.commit.side_effect = RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        await repo.update(row.id, item_name="Updated platter")

    session.rollback.assert_awaited_once()
