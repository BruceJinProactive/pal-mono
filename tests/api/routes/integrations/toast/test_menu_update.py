from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from api.routes.integrations.toast.schema import ToastWebhookRequest

MODULE = "api.routes.integrations.toast._utils"


async def _run_in_threadpool_now(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    return func(*args, **kwargs)


def _toast_menu_request(
    published_date: str = "2026-05-14T12:00:00.000Z",
) -> ToastWebhookRequest:
    return ToastWebhookRequest(
        timestamp="2026-05-14T12:00:01.000Z",
        eventCategory="menus",
        eventType="menus.updated",
        guid="event-guid",
        details={
            "restaurantGuid": "restaurant-guid",
            "publishedDate": published_date,
        },
    )


def test_find_toast_project_integrations_loads_projects_for_matching_integrations() -> (
    None
):
    from api.routes.integrations.toast._utils import (
        _find_toast_project_integrations_by_restaurant_guid,
    )

    session = MagicMock()
    project_one = SimpleNamespace(name="One")
    integration_one = SimpleNamespace(project_id="project-1")
    project_two = SimpleNamespace(name="Two")
    integration_two = SimpleNamespace(project_id="project-2")

    with (
        patch(f"{MODULE}.ProjectIntegrationRepository") as pi_repo_cls,
        patch(f"{MODULE}.ProjectRepository") as project_repo_cls,
    ):
        pi_repo = pi_repo_cls.return_value
        pi_repo.get_project_integrations_by_store_identifier_and_provider.return_value = [
            integration_one,
            integration_two,
        ]
        project_repo = project_repo_cls.return_value
        project_repo.get_project.side_effect = [project_one, project_two]

        result = _find_toast_project_integrations_by_restaurant_guid(
            "restaurant-guid", session
        )

    assert result == [(project_one, integration_one), (project_two, integration_two)]
    pi_repo.get_project_integrations_by_store_identifier_and_provider.assert_called_once()
    assert project_repo.get_project.call_args_list[0].args == ("project-1",)
    assert project_repo.get_project.call_args_list[1].args == ("project-2",)


def test_find_toast_project_integrations_returns_empty_when_none_found() -> None:
    from api.routes.integrations.toast._utils import (
        _find_toast_project_integrations_by_restaurant_guid,
    )

    session = MagicMock()

    with patch(f"{MODULE}.ProjectIntegrationRepository") as pi_repo_cls:
        pi_repo = pi_repo_cls.return_value
        pi_repo.get_project_integrations_by_store_identifier_and_provider.return_value = (
            []
        )

        result = _find_toast_project_integrations_by_restaurant_guid(
            "restaurant-guid", session
        )

    assert result == []


def test_find_toast_project_integrations_skips_missing_projects() -> None:
    from api.routes.integrations.toast._utils import (
        _find_toast_project_integrations_by_restaurant_guid,
    )

    session = MagicMock()
    project_integration = SimpleNamespace(id="pi-1", project_id="missing-project")

    with (
        patch(f"{MODULE}.ProjectIntegrationRepository") as pi_repo_cls,
        patch(f"{MODULE}.ProjectRepository") as project_repo_cls,
    ):
        pi_repo = pi_repo_cls.return_value
        pi_repo.get_project_integrations_by_store_identifier_and_provider.return_value = [
            project_integration
        ]
        project_repo = project_repo_cls.return_value
        project_repo.get_project.return_value = None

        result = _find_toast_project_integrations_by_restaurant_guid(
            "restaurant-guid", session
        )

    assert result == []


def test_get_menu_last_updated_returns_none_for_empty_config() -> None:
    from api.routes.integrations.toast._utils import _get_menu_last_updated

    assert _get_menu_last_updated(None) is None
    assert _get_menu_last_updated({}) is None


def test_get_selected_menus_reads_legacy_menus_key() -> None:
    from api.routes.integrations.toast._utils import _get_selected_menus

    assert _get_selected_menus({"menus": ["Lunch Menu"]}) == ["Lunch Menu"]


def test_get_selected_menus_prefers_selected_menus_over_legacy_menus() -> None:
    from api.routes.integrations.toast._utils import _get_selected_menus

    assert _get_selected_menus(
        {"selected_menus": ["Dinner Menu"], "menus": ["Lunch Menu"]}
    ) == ["Dinner Menu"]


def test_get_make_unique_defaults_to_true() -> None:
    from api.routes.integrations.toast._utils import _get_make_unique

    assert _get_make_unique({}) is True
    assert _get_make_unique({"selected_menus": ["Dinner Menu"]}) is True


def test_get_make_unique_reads_boolean_config() -> None:
    from api.routes.integrations.toast._utils import _get_make_unique

    assert _get_make_unique({"make_unique": False}) is False
    assert _get_make_unique({"make_unique": True}) is True


@pytest.mark.asyncio
async def test_update_menu_content_generates_and_persists_toast_menu_assets() -> None:
    from api.routes.integrations.toast._utils import update_menu_content

    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    project = SimpleNamespace(name="Pepperonis", product_info="old menu")
    project_integration = SimpleNamespace(
        id=uuid4(),
        config={
            "submit_orders": False,
            "selected_menus": ["Dine-In Menu"],
            "make_unique": False,
        },
    )
    raw_menu = {
        "menus": [
            {"name": "Dine-In Menu", "guid": "menu-guid"},
            {"name": "Hidden Menu", "guid": "menu-guid"},
            {"name": "dine-in menu", "guid": "lowercase-menu-guid"},
        ]
    }
    compiled_menu = {"menus": {"menu-guid": {"name": "Main"}}}
    prompt_context = "compiled prompt context"

    with (
        patch(f"{MODULE}.run_in_threadpool", _run_in_threadpool_now),
        patch(f"{MODULE}.SyncSessionLocal", return_value=session_context),
        patch(
            f"{MODULE}._find_toast_project_integrations_by_restaurant_guid",
            return_value=[(project, project_integration)],
        ) as mock_find,
        patch(
            f"{MODULE}.get_toast_access_token_from_aws", return_value="token"
        ) as mock_token,
        patch(f"{MODULE}.download_menu", return_value=raw_menu) as mock_download_menu,
        patch(
            f"{MODULE}.compile_toast_menu_v2", return_value=compiled_menu
        ) as mock_compile,
        patch(
            f"{MODULE}.build_toast_lookup_prompt_context_markdown",
            return_value=prompt_context,
        ) as mock_prompt,
    ):
        await update_menu_content(_toast_menu_request())

    mock_find.assert_called_once_with("restaurant-guid", session)
    mock_token.assert_called_once_with()
    mock_download_menu.assert_called_once_with("token", "restaurant-guid")
    mock_compile.assert_called_once_with(
        raw_menu,
        selected_menus=["Dine-In Menu"],
        make_unique_menus=None,
        remove_unused_weights=True,
    )
    mock_prompt.assert_called_once_with(compiled_menu)
    assert project.product_info == prompt_context
    assert project_integration.config == {
        "submit_orders": False,
        "selected_menus": ["Dine-In Menu"],
        "make_unique": False,
        "menu_data": compiled_menu,
        "menu_last_updated": "2026-05-14T12:00:00.000Z",
    }
    session.add.assert_any_call(project)
    session.add.assert_any_call(project_integration)
    session.commit.assert_called_once_with()


@pytest.mark.asyncio
async def test_update_menu_content_raises_when_configured_menu_is_missing() -> None:
    from api.routes.integrations.toast._utils import update_menu_content

    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    project = SimpleNamespace(name="Pepperonis", product_info="old menu")
    project_integration = SimpleNamespace(
        id=uuid4(),
        config={"selected_menus": ["Missing Menu"]},
    )
    raw_menu = {"menus": [{"name": "Dine-In Menu", "guid": "menu-guid"}]}

    with (
        patch(f"{MODULE}.run_in_threadpool", _run_in_threadpool_now),
        patch(f"{MODULE}.SyncSessionLocal", return_value=session_context),
        patch(
            f"{MODULE}._find_toast_project_integrations_by_restaurant_guid",
            return_value=[(project, project_integration)],
        ),
        patch(f"{MODULE}.get_toast_access_token_from_aws", return_value="token"),
        patch(f"{MODULE}.download_menu", return_value=raw_menu),
        patch(
            f"{MODULE}.compile_toast_menu_v2",
            side_effect=ValueError("Selected menu names not found"),
        ) as mock_compile,
    ):
        with pytest.raises(
            ValueError,
            match="Selected menu names not found",
        ):
            await update_menu_content(_toast_menu_request())

    mock_compile.assert_called_once_with(
        raw_menu,
        selected_menus=["Missing Menu"],
        make_unique_menus=["Missing Menu"],
        remove_unused_weights=True,
    )
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_menu_content_raises_when_configured_filter_has_malformed_menu_payload() -> (
    None
):
    from api.routes.integrations.toast._utils import update_menu_content

    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    project = SimpleNamespace(name="Pepperonis", product_info="old menu")
    project_integration = SimpleNamespace(
        id=uuid4(),
        config={"selected_menus": ["Dine-In Menu"]},
    )
    raw_menu = {"menus": {"name": "Dine-In Menu", "guid": "menu-guid"}}

    with (
        patch(f"{MODULE}.run_in_threadpool", _run_in_threadpool_now),
        patch(f"{MODULE}.SyncSessionLocal", return_value=session_context),
        patch(
            f"{MODULE}._find_toast_project_integrations_by_restaurant_guid",
            return_value=[(project, project_integration)],
        ),
        patch(f"{MODULE}.get_toast_access_token_from_aws", return_value="token"),
        patch(f"{MODULE}.download_menu", return_value=raw_menu),
        patch(
            f"{MODULE}.compile_toast_menu_v2",
            side_effect=ValueError("Field 'menus' must be an array"),
        ) as mock_compile,
    ):
        with pytest.raises(
            ValueError,
            match="Field 'menus' must be an array",
        ):
            await update_menu_content(_toast_menu_request())

    mock_compile.assert_called_once_with(
        raw_menu,
        selected_menus=["Dine-In Menu"],
        make_unique_menus=["Dine-In Menu"],
        remove_unused_weights=True,
    )
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_menu_content_skips_when_published_menu_is_current() -> None:
    from api.routes.integrations.toast._utils import update_menu_content

    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    project = SimpleNamespace(name="Pepperonis", product_info="old menu")
    project_integration = SimpleNamespace(
        id=uuid4(),
        config={
            "menu_data": {"existing": True},
            "menu_last_updated": "2026-05-14T12:00:00.000Z",
        },
    )

    with (
        patch(f"{MODULE}.run_in_threadpool", _run_in_threadpool_now),
        patch(f"{MODULE}.SyncSessionLocal", return_value=session_context),
        patch(
            f"{MODULE}._find_toast_project_integrations_by_restaurant_guid",
            return_value=[(project, project_integration)],
        ),
        patch(f"{MODULE}.download_menu") as mock_download_menu,
        patch(f"{MODULE}.compile_toast_menu_v2") as mock_compile,
        patch(f"{MODULE}.build_toast_lookup_prompt_context_markdown") as mock_prompt,
    ):
        await update_menu_content(_toast_menu_request())

    mock_download_menu.assert_not_called()
    mock_compile.assert_not_called()
    mock_prompt.assert_not_called()
    assert project.product_info == "old menu"
    assert project_integration.config == {
        "menu_data": {"existing": True},
        "menu_last_updated": "2026-05-14T12:00:00.000Z",
    }
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_menu_content_skips_when_incoming_menu_is_older() -> None:
    from api.routes.integrations.toast._utils import update_menu_content

    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    project = SimpleNamespace(name="Pepperonis", product_info="newer menu")
    project_integration = SimpleNamespace(
        id=uuid4(),
        config={
            "menu_data": {"existing": True},
            "menu_last_updated": "2026-05-14T13:00:00.000Z",
        },
    )

    with (
        patch(f"{MODULE}.run_in_threadpool", _run_in_threadpool_now),
        patch(f"{MODULE}.SyncSessionLocal", return_value=session_context),
        patch(
            f"{MODULE}._find_toast_project_integrations_by_restaurant_guid",
            return_value=[(project, project_integration)],
        ),
        patch(f"{MODULE}.download_menu") as mock_download_menu,
        patch(f"{MODULE}.compile_toast_menu_v2") as mock_compile,
        patch(f"{MODULE}.build_toast_lookup_prompt_context_markdown") as mock_prompt,
    ):
        await update_menu_content(_toast_menu_request("2026-05-14T12:00:00.000Z"))

    mock_download_menu.assert_not_called()
    mock_compile.assert_not_called()
    mock_prompt.assert_not_called()
    assert project.product_info == "newer menu"
    assert project_integration.config == {
        "menu_data": {"existing": True},
        "menu_last_updated": "2026-05-14T13:00:00.000Z",
    }
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_menu_content_rolls_back_when_menu_generation_fails() -> None:
    from api.routes.integrations.toast._utils import update_menu_content

    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    session_context.__exit__.return_value = False

    project = SimpleNamespace(name="Pepperonis", product_info="old menu")
    project_integration = SimpleNamespace(id=uuid4(), config={})

    with (
        patch(f"{MODULE}.run_in_threadpool", _run_in_threadpool_now),
        patch(f"{MODULE}.SyncSessionLocal", return_value=session_context),
        patch(
            f"{MODULE}._find_toast_project_integrations_by_restaurant_guid",
            return_value=[(project, project_integration)],
        ),
        patch(
            f"{MODULE}.get_toast_access_token_from_aws",
            side_effect=RuntimeError("token failed"),
        ),
    ):
        with pytest.raises(RuntimeError, match="token failed"):
            await update_menu_content(_toast_menu_request())

    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()
