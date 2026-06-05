import uuid
from unittest.mock import MagicMock, patch

from api.routes.admin._subscription import retrieve_projects


@patch("api.routes.admin._subscription.project_service")
def test_retrieve_projects_returns_empty_list_without_project_ids(
    mock_project_service: MagicMock,
) -> None:
    projects = retrieve_projects(MagicMock(), uuid.uuid4(), None)

    assert projects == []
    mock_project_service.get_projects_by_ids.assert_not_called()


@patch("api.routes.admin._subscription.project_service")
def test_retrieve_projects_fetches_projects_by_ids(
    mock_project_service: MagicMock,
) -> None:
    session = MagicMock()
    account_id = uuid.uuid4()
    project_id = uuid.uuid4()
    project = MagicMock()
    project.id = project_id
    project.account_id = account_id
    mock_project_service.get_projects_by_ids.return_value = [project]

    projects = retrieve_projects(session, account_id, [project_id])

    assert projects == [project]
    mock_project_service.get_projects_by_ids.assert_called_once_with(
        session, [project_id]
    )
