"""Tests for db.pal_repository.CateringRequestActivityRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.catering_request_activity import (
    CateringRequestActivityRepository,
    _to_data,
)
from db.pal_repository.data_classes.catering_request_activity import (
    CateringRequestActivityData,
)
from db.tables.catering_request_activities import (
    CateringRequestActivity,
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo(mock_session: AsyncMock) -> CateringRequestActivityRepository:
    return CateringRequestActivityRepository(mock_session)


def _make_activity_data(**overrides) -> CateringRequestActivityData:
    now = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "catering_request_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "activity_type": CateringRequestActivityType.REQUEST_CREATED,
        "actor_type": CateringRequestActivityActorType.CUSTOMER,
        "actor_id": None,
        "actor_display_name": "Maya Acme",
        "description": "Catering request created.",
        "metadata": {"initial_fields": {"party_size": 45}},
        "schema_version": 1,
        "source": CateringRequestActivitySource.AI_AGENT,
        "occurred_at": now,
        "created_at": now,
    }
    defaults.update(overrides)
    return CateringRequestActivityData(**defaults)


def _make_orm_row(activity: CateringRequestActivityData) -> MagicMock:
    row = MagicMock(spec=CateringRequestActivity)
    row.id = activity.id
    row.catering_request_id = activity.catering_request_id
    row.project_id = activity.project_id
    row.activity_type = activity.activity_type
    row.actor_type = activity.actor_type
    row.actor_id = activity.actor_id
    row.actor_display_name = activity.actor_display_name
    row.description = activity.description
    row.activity_metadata = dict(activity.metadata)
    row.schema_version = activity.schema_version
    row.source = activity.source
    row.occurred_at = activity.occurred_at
    row.created_at = activity.created_at
    return row


def test_to_data_converts_orm_row() -> None:
    activity = _make_activity_data()
    row = _make_orm_row(activity)

    data = _to_data(row)

    assert data == activity
    assert data.metadata == {"initial_fields": {"party_size": 45}}


@pytest.mark.asyncio
async def test_create_persists_activity(
    repo: CateringRequestActivityRepository,
    mock_session: AsyncMock,
) -> None:
    activity = _make_activity_data()

    result = await repo.create(activity)

    assert result.id == activity.id
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_by_request_returns_activities(
    repo: CateringRequestActivityRepository,
    mock_session: AsyncMock,
) -> None:
    activity = _make_activity_data()
    row = _make_orm_row(activity)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [row]
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result

    results = await repo.list_by_request(
        project_id=activity.project_id,
        catering_request_id=activity.catering_request_id,
    )

    assert results == [activity]


@pytest.mark.asyncio
async def test_list_by_request_rolls_back_on_error(
    repo: CateringRequestActivityRepository,
    mock_session: AsyncMock,
) -> None:
    mock_session.execute.side_effect = SQLAlchemyError("db error")

    with pytest.raises(SQLAlchemyError):
        await repo.list_by_request(
            project_id=uuid.uuid4(),
            catering_request_id=uuid.uuid4(),
        )

    mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_by_request_returns_deleted_row_count(
    repo: CateringRequestActivityRepository,
    mock_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_session.execute.return_value = mock_result

    result = await repo.delete_by_request(
        project_id=uuid.uuid4(),
        catering_request_id=uuid.uuid4(),
    )

    assert result == 3
    mock_session.execute.assert_awaited_once()
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_by_request_returns_zero_when_rowcount_missing(
    repo: CateringRequestActivityRepository,
    mock_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.rowcount = None
    mock_session.execute.return_value = mock_result

    result = await repo.delete_by_request(
        project_id=uuid.uuid4(),
        catering_request_id=uuid.uuid4(),
    )

    assert result == 0


@pytest.mark.asyncio
async def test_delete_by_request_rolls_back_on_error(
    repo: CateringRequestActivityRepository,
    mock_session: AsyncMock,
) -> None:
    mock_session.execute.side_effect = SQLAlchemyError("db error")

    with pytest.raises(SQLAlchemyError):
        await repo.delete_by_request(
            project_id=uuid.uuid4(),
            catering_request_id=uuid.uuid4(),
        )

    mock_session.rollback.assert_awaited_once()
