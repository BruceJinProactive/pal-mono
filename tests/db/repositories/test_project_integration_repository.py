from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import SQLAlchemyError

from db.repositories.project_integration_repository import (
    ProjectIntegrationRepository,
    ProjectIntegrationRepositoryAsync,
)
from db.tables.types import IntegrationProvider


def _repo_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.join.return_value = query
    query.filter.return_value = query
    return session, query


def test_get_project_integrations_by_store_identifier_and_provider() -> None:
    session, query = _repo_session()
    project_integrations = [MagicMock()]
    query.all.return_value = project_integrations
    repo = ProjectIntegrationRepository(session)

    result = repo.get_project_integrations_by_store_identifier_and_provider(
        "restaurant-guid",
        IntegrationProvider.toast,
    )

    assert result == project_integrations
    session.query.assert_called_once()
    query.join.assert_called_once()
    assert query.filter.call_count == 2


def test_get_project_integrations_by_store_identifier_and_provider_rolls_back_on_error() -> (
    None
):
    session, query = _repo_session()
    query.all.side_effect = SQLAlchemyError("query failed")
    repo = ProjectIntegrationRepository(session)

    result = repo.get_project_integrations_by_store_identifier_and_provider(
        "restaurant-guid",
        IntegrationProvider.toast,
    )

    assert result == []
    session.rollback.assert_called_once_with()


async def test_async_get_project_integrations_by_store_identifier_and_provider() -> (
    None
):
    session = AsyncMock()
    project_integrations = [MagicMock()]
    result = MagicMock()
    result.scalars.return_value.all.return_value = project_integrations
    session.execute.return_value = result
    repo = ProjectIntegrationRepositoryAsync(session)

    found = await repo.get_project_integrations_by_store_identifier_and_provider(
        "restaurant-guid",
        IntegrationProvider.toast,
    )

    assert found == project_integrations
    session.execute.assert_awaited_once()


async def test_async_get_project_integrations_by_store_identifier_and_provider_rolls_back_on_error() -> (
    None
):
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("query failed")
    repo = ProjectIntegrationRepositoryAsync(session)

    result = await repo.get_project_integrations_by_store_identifier_and_provider(
        "restaurant-guid",
        IntegrationProvider.toast,
    )

    assert result == []
    session.rollback.assert_awaited_once_with()
