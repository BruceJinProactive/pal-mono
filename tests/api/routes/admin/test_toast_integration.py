"""Tests for Toast integration endpoints."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin._integration import _compile_toast_config
from api.routes.admin._toast_integration import (
    _extract_menu_names,
    _parse_dining_options,
    _suggest_guids,
    get_toast_options,
)
from api.schemas.admin.integration import CreateProjectIntegrationRequest
from api.schemas.admin.pos_onboarding import DiningOption

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.username = str(uuid.uuid4())
    return ctx


def _make_account(name: str = "bobs-pizza") -> MagicMock:
    acct = MagicMock()
    acct.id = uuid.uuid4()
    acct.name = name
    return acct


def _make_integration(secret_key: str = "KEY123") -> MagicMock:
    integ = MagicMock()
    integ.id = uuid.uuid4()
    integ.secret_key = secret_key
    return integ


def _raw_menu(names: list[str]) -> dict:
    return {"menus": [{"name": n, "menuGroups": []} for n in names]}


def _dining_options_json(options: list[dict]) -> str:
    return json.dumps(options)


# ---------------------------------------------------------------------------
# Unit: CreateProjectIntegrationRequest toast_v3 validation
# ---------------------------------------------------------------------------


class TestToastV3ConfigValidation:
    def _make(
        self,
        config: dict,
        tool_name: str = "toast_v3",
        auto_fetch: bool = False,
    ) -> CreateProjectIntegrationRequest:
        return CreateProjectIntegrationRequest(
            integration_id=uuid.uuid4(),
            store_identifier="rest-guid",
            tool_name=tool_name,
            config=config,
            auto_fetch=auto_fetch,
        )

    def test_auto_fetch_path_valid(self) -> None:
        """auto_fetch=True with restaurant_guid only is valid."""
        req = self._make({"restaurant_guid": "rg-123"}, auto_fetch=True)
        assert req.auto_fetch is True

    def test_manual_path_valid(self) -> None:
        """auto_fetch=False with full config is valid."""
        req = self._make(
            {
                "restaurant_guid": "rg-123",
                "menu_data": {"items": []},
                "takeout_dining_option_guid": "t-guid",
            }
        )
        assert req.config["menu_data"] == {"items": []}

    def test_missing_restaurant_guid_raises(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="restaurant_guid"):
            self._make({"takeout_dining_option_guid": "t-guid"})

    def test_empty_restaurant_guid_raises(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="restaurant_guid"):
            self._make({"restaurant_guid": "   "})

    def test_auto_fetch_with_menu_data_raises(self) -> None:
        """auto_fetch=True must not have menu_data already set."""
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="menu_data"):
            self._make(
                {"restaurant_guid": "rg-123", "menu_data": {"items": []}},
                auto_fetch=True,
            )

    def test_manual_empty_menu_data_raises(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="menu_data"):
            self._make({"restaurant_guid": "rg-123", "menu_data": {}})

    def test_manual_without_takeout_guid_raises(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="takeout_dining_option_guid"):
            self._make({"restaurant_guid": "rg-123", "menu_data": {"items": []}})

    def test_non_toast_tool_skips_validation(self) -> None:
        req = self._make({}, tool_name="adora_v3")
        assert req.config == {}


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------


class TestExtractMenuNames:
    def test_returns_names(self) -> None:
        raw = _raw_menu(["Lunch Menu", "Dinner Menu"])
        assert _extract_menu_names(raw) == ["Lunch Menu", "Dinner Menu"]

    def test_skips_entries_without_name(self) -> None:
        raw = {"menus": [{"menuGroups": []}, {"name": "Dinner Menu"}]}
        assert _extract_menu_names(raw) == ["Dinner Menu"]

    def test_empty_menus(self) -> None:
        assert _extract_menu_names({"menus": []}) == []

    def test_missing_menus_key(self) -> None:
        assert _extract_menu_names({}) == []


class TestParseDiningOptions:
    def test_parses_valid_options(self) -> None:
        raw = _dining_options_json(
            [
                {"guid": "aaa", "name": "Takeout", "behavior": "TAKE_OUT"},
                {"guid": "bbb", "name": "Delivery", "behavior": "DELIVERY"},
            ]
        )
        opts = _parse_dining_options(raw)
        assert len(opts) == 2
        assert opts[0].guid == "aaa"
        assert opts[0].behavior == "TAKE_OUT"

    def test_skips_entries_without_guid_or_name(self) -> None:
        raw = _dining_options_json(
            [
                {"name": "No GUID", "behavior": "TAKE_OUT"},
                {"guid": "ccc", "behavior": "DELIVERY"},  # no name
                {"guid": "ddd", "name": "Valid", "behavior": "DINE_IN"},
            ]
        )
        opts = _parse_dining_options(raw)
        assert len(opts) == 1
        assert opts[0].guid == "ddd"

    def test_invalid_json_returns_empty(self) -> None:
        assert _parse_dining_options("not-json") == []

    def test_empty_list(self) -> None:
        assert _parse_dining_options("[]") == []


class TestSuggestGuids:
    def test_single_takeout_suggested(self) -> None:
        opts = [
            DiningOption(guid="t1", name="Takeout", behavior="TAKE_OUT"),
            DiningOption(guid="d1", name="Dine In", behavior="DINE_IN"),
        ]
        takeout, delivery = _suggest_guids(opts)
        assert takeout == "t1"
        assert delivery is None

    def test_ambiguous_takeout_not_suggested(self) -> None:
        opts = [
            DiningOption(guid="t1", name="Takeout 1", behavior="TAKE_OUT"),
            DiningOption(guid="t2", name="Takeout 2", behavior="TAKE_OUT"),
        ]
        takeout, delivery = _suggest_guids(opts)
        assert takeout is None

    def test_single_delivery_suggested(self) -> None:
        opts = [
            DiningOption(guid="d1", name="Delivery", behavior="DELIVERY"),
        ]
        _, delivery = _suggest_guids(opts)
        assert delivery == "d1"

    def test_no_options(self) -> None:
        assert _suggest_guids([]) == (None, None)


# ---------------------------------------------------------------------------
# Integration: get_toast_options handler
# ---------------------------------------------------------------------------


class TestGetToastOptions:
    def _make_session(self) -> MagicMock:
        return MagicMock()

    def test_returns_options_when_valid(self) -> None:
        session = MagicMock()
        account = _make_account()
        integration = _make_integration("SK1")
        credentials = {"client_id": "cid", "client_secret": "csec"}
        raw_menu = _raw_menu(["Lunch Menu", "Test Menu"])
        dining_json = _dining_options_json(
            [
                {"guid": "t1", "name": "Takeout", "behavior": "TAKE_OUT"},
            ]
        )

        with (
            patch("api.routes.admin._toast_integration.db.AccountRepository") as ar,
            patch("api.routes.admin._toast_integration.db.IntegrationRepository") as ir,
            patch(
                "api.routes.admin._toast_integration._get_integration_credentials",
                return_value=credentials,
            ),
            patch(
                "api.routes.admin._toast_integration.get_toast_access_token",
                return_value=MagicMock(),
            ),
            patch(
                "api.routes.admin._toast_integration.download_menu",
                return_value=raw_menu,
            ),
            patch(
                "api.routes.admin._toast_integration.get_dining_options",
                return_value=dining_json,
            ),
        ):
            ar.return_value.get_account.return_value = account
            ir.return_value.get_integration_by_id.return_value = integration

            result = get_toast_options(
                "bobs-pizza",
                integration.id,
                "rest-guid-123",
                _make_context(),
                session,
            )

        assert result.available_menus == ["Lunch Menu", "Test Menu"]
        assert len(result.dining_options) == 1
        assert result.suggested_takeout_guid == "t1"
        assert result.suggested_delivery_guid is None

    def test_raises_404_when_account_not_found(self) -> None:
        session = MagicMock()
        with patch("api.routes.admin._toast_integration.db.AccountRepository") as ar:
            ar.return_value.get_account.return_value = None
            with pytest.raises(HTTPException) as exc:
                get_toast_options(
                    "no-account",
                    uuid.uuid4(),
                    "rguid",
                    _make_context(),
                    session,
                )
        assert exc.value.status_code == 404

    def test_raises_404_when_integration_not_found(self) -> None:
        session = MagicMock()
        account = _make_account()
        with (
            patch("api.routes.admin._toast_integration.db.AccountRepository") as ar,
            patch("api.routes.admin._toast_integration.db.IntegrationRepository") as ir,
        ):
            ar.return_value.get_account.return_value = account
            ir.return_value.get_integration_by_id.return_value = None
            with pytest.raises(HTTPException) as exc:
                get_toast_options(
                    "bobs-pizza",
                    uuid.uuid4(),
                    "rguid",
                    _make_context(),
                    session,
                )
        assert exc.value.status_code == 404

    def test_raises_400_when_toast_auth_fails(self) -> None:
        session = MagicMock()
        account = _make_account()
        integration = _make_integration("SK2")
        with (
            patch("api.routes.admin._toast_integration.db.AccountRepository") as ar,
            patch("api.routes.admin._toast_integration.db.IntegrationRepository") as ir,
            patch(
                "api.routes.admin._toast_integration._get_integration_credentials",
                return_value={"client_id": "cid", "client_secret": "csec"},
            ),
            patch(
                "api.routes.admin._toast_integration.get_toast_access_token",
                return_value=None,
            ),
        ):
            ar.return_value.get_account.return_value = account
            ir.return_value.get_integration_by_id.return_value = integration
            with pytest.raises(HTTPException) as exc:
                get_toast_options(
                    "bobs-pizza",
                    integration.id,
                    "rguid",
                    _make_context(),
                    session,
                )
        assert exc.value.status_code == 400
        assert "authentication" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# Integration: _compile_toast_config
# ---------------------------------------------------------------------------


class TestCompileToastConfig:
    def _make_request(
        self,
        restaurant_guid: str | None = "rest-guid-123",
        takeout_dining_option_guid: str | None = "t-guid",
        delivery_dining_option_guid: str | None = None,
        selected_menus: list[str] | None = None,
        menu_data: dict | None = None,
    ) -> CreateProjectIntegrationRequest:
        config: dict = {}
        if restaurant_guid:
            config["restaurant_guid"] = restaurant_guid
        if takeout_dining_option_guid:
            config["takeout_dining_option_guid"] = takeout_dining_option_guid
        if delivery_dining_option_guid:
            config["delivery_dining_option_guid"] = delivery_dining_option_guid
        if selected_menus:
            config["selected_menus"] = selected_menus
        if menu_data:
            config["menu_data"] = menu_data
        return CreateProjectIntegrationRequest(
            integration_id=uuid.uuid4(),
            store_identifier="rest-guid-123",
            tool_name="toast_v3",
            config=config,
            auto_fetch=True,
        )

    def _mock_session(self, integration: MagicMock | None) -> MagicMock:
        """Return a mock SyncSessionLocal context manager yielding a session with integration."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = integration
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx

    def test_no_selected_menus_compiles_all(self) -> None:
        """When selected_menus is absent, all menus are compiled."""
        req = self._make_request(selected_menus=None)
        integration = _make_integration("SK5")
        compiled = {"restaurant_guid": "rest-guid-123", "items": []}

        with (
            patch(
                "db.session.SyncSessionLocal",
                return_value=self._mock_session(integration),
            ),
            patch(
                "api.routes.admin._integration._get_integration_credentials",
                return_value={"client_id": "cid", "client_secret": "csec"},
            ),
            patch(
                "api.routes.admin._integration.get_toast_access_token",
                return_value=MagicMock(),
            ),
            patch(
                "api.routes.admin._integration.download_menu",
                return_value={"menus": []},
            ),
            patch(
                "api.routes.admin._integration.compile_toast_menu_v2",
                return_value=compiled,
            ) as mock_compile,
        ):
            _compile_toast_config(req, uuid.uuid4())

        mock_compile.assert_called_once()
        _, kwargs = mock_compile.call_args
        assert kwargs.get("selected_menus") is None

    def test_populates_menu_data_in_config(self) -> None:
        req = self._make_request()
        integration = _make_integration("SK3")
        compiled = {"restaurant_guid": "rest-guid-123", "items": []}

        with (
            patch(
                "db.session.SyncSessionLocal",
                return_value=self._mock_session(integration),
            ),
            patch(
                "api.routes.admin._integration._get_integration_credentials",
                return_value={"client_id": "cid", "client_secret": "csec"},
            ),
            patch(
                "api.routes.admin._integration.get_toast_access_token",
                return_value=MagicMock(),
            ),
            patch(
                "api.routes.admin._integration.download_menu",
                return_value={"menus": []},
            ),
            patch(
                "api.routes.admin._integration.compile_toast_menu_v2",
                return_value=compiled,
            ),
        ):
            result = _compile_toast_config(req, uuid.uuid4())

        assert result.config["menu_data"] == compiled
        assert result.config["takeout_dining_option_guid"] == "t-guid"
        assert result.config["submit_orders"] is False

    def test_raises_404_when_integration_missing(self) -> None:
        req = self._make_request()
        with (
            patch("db.session.SyncSessionLocal", return_value=self._mock_session(None)),
        ):
            with pytest.raises(HTTPException) as exc:
                _compile_toast_config(req, uuid.uuid4())
        assert exc.value.status_code == 404

    def test_raises_400_when_auth_fails(self) -> None:
        req = self._make_request()
        integration = _make_integration("SK4")

        with (
            patch(
                "db.session.SyncSessionLocal",
                return_value=self._mock_session(integration),
            ),
            patch(
                "api.routes.admin._integration._get_integration_credentials",
                return_value={"client_id": "cid", "client_secret": "csec"},
            ),
            patch(
                "api.routes.admin._integration.get_toast_access_token",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                _compile_toast_config(req, uuid.uuid4())
        assert exc.value.status_code == 400
