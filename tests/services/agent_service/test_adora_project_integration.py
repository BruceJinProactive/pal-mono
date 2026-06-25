import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pal_agents.spec import AdoraSpec

from services.agent_service._implementation import (
    _build_specs_from_project_integrations,
    _resolve_integration_credentials,
)
from services.agent_service._pal_agent_tool_registry import (
    _build_adora_v3_spec,
    merge_auth_with_credentials,
)


def _make_project_integration(
    *,
    tool_name: str = "adora_v3",
    store_identifier: str = "UGDX4",
    config: dict | None = None,
    integration_id: uuid.UUID | None = None,
):
    pi = MagicMock()
    pi.tool_name = tool_name
    pi.store_identifier = store_identifier
    pi.config = config or {}
    pi.integration_id = integration_id or uuid.uuid4()
    return pi


def _make_integration_record(
    *,
    client_id: str = "test-api-key",
    client_secret: str = "test-api-secret",
    secret_key: str | None = None,
):
    record = MagicMock()
    record.id = uuid.uuid4()
    record.client_id = client_id
    record.client_secret = client_secret
    record.secret_key = secret_key
    return record


# ---------------------------------------------------------------------------
# _merge_auth_with_credentials
# ---------------------------------------------------------------------------


class TestMergeAuthWithCredentials:
    def test_no_credentials_returns_original(self):
        auth = {"type": "bearer", "token": "static"}
        result = merge_auth_with_credentials(auth, None, None)
        assert result == auth

    def test_no_auth_config_with_default_url_builds_rotating_bearer(self):
        result = merge_auth_with_credentials(
            None, "my-id", "my-secret", default_token_url="https://example.com/token"
        )
        assert result is not None
        assert result["type"] == "bearer"
        assert result["rotation"]["enabled"] is True
        assert result["rotation"]["client_id"] == "my-id"
        assert result["rotation"]["client_secret"] == "my-secret"
        assert result["rotation"]["token_url"] == "https://example.com/token"

    def test_no_auth_config_without_default_url_returns_none(self):
        result = merge_auth_with_credentials(None, "my-id", "my-secret")
        assert result is None

    def test_bearer_rotation_injects_credentials(self):
        auth = {
            "type": "bearer",
            "rotation": {
                "enabled": True,
                "token_url": "https://custom.endpoint/token",
            },
        }
        result = merge_auth_with_credentials(auth, "cid", "csecret")
        assert result is not None
        assert result["rotation"]["client_id"] == "cid"
        assert result["rotation"]["client_secret"] == "csecret"
        assert result["rotation"]["token_url"] == "https://custom.endpoint/token"

    def test_basic_auth_injects_credentials(self):
        auth = {"type": "basic"}
        result = merge_auth_with_credentials(auth, "user", "pass")
        assert result is not None
        assert result["username"] == "user"
        assert result["password"] == "pass"

    def test_no_credentials_no_config_returns_none(self):
        result = merge_auth_with_credentials(None, None, None)
        assert result is None


# ---------------------------------------------------------------------------
# _build_adora_v3_spec (pure function, no DB)
# ---------------------------------------------------------------------------


class TestBuildAdoraV3Spec:
    def test_basic_config(self):
        config = {
            "menu_data": {"categories": [{"name": "Pizza"}]},
            "base_url": "https://api.adora.net",
        }
        result = _build_adora_v3_spec(config, "UGDX4", "cid", "csecret", None)

        assert isinstance(result, AdoraSpec)
        assert result.enabled is True
        assert result.menu_data == config["menu_data"]
        assert result.store_id == "UGDX4"
        assert result.base_url == "https://api.adora.net"
        assert result.auth is not None
        assert result.auth["type"] == "bearer"
        assert result.auth["rotation"]["client_id"] == "cid"

    def test_auth_from_config_merged_with_credentials(self):
        config = {
            "menu_data": {},
            "auth": {
                "type": "bearer",
                "rotation": {
                    "enabled": True,
                    "token_url": "https://custom/token",
                },
            },
        }
        result = _build_adora_v3_spec(config, "S1", "k", "s", None)

        assert result.auth is not None
        assert result.auth["rotation"]["token_url"] == "https://custom/token"
        assert result.auth["rotation"]["client_id"] == "k"
        assert result.auth["rotation"]["client_secret"] == "s"

    def test_no_credentials_no_auth(self):
        config = {"menu_data": {}}
        result = _build_adora_v3_spec(config, "S1", None, None, None)

        assert result.enabled is True
        assert not hasattr(result, "auth") or result.auth is None

    def test_all_config_fields_forwarded(self):
        config = {
            "menu_data": {"items": []},
            "coupon_data": {"coupons": []},
            "base_url": "https://api.test.com",
            "timeout": 30.0,
            "debug": True,
            "force_payment_link": True,
            "no_delivery_entries": True,
            "loyalty_points_per_dollar": 10,
            "enable_customer_discounts": True,
            "customer_email": "test@example.com",
        }
        result = _build_adora_v3_spec(config, "STORE1", "k", "s", None)

        assert result.store_id == "STORE1"
        assert result.coupon_data == {"coupons": []}
        assert result.base_url == "https://api.test.com"
        assert result.timeout == 30.0
        assert result.debug is True
        assert result.force_payment_link is True
        assert result.no_delivery_entries is True
        assert result.loyalty_points_per_dollar == 10
        assert result.enable_customer_discounts is True
        assert result.customer_email == "test@example.com"


# ---------------------------------------------------------------------------
# _build_specs_from_project_integrations (registry dispatch)
# ---------------------------------------------------------------------------


class TestBuildSpecsFromProjectIntegrations:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_matches(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value = iter([])
        session.execute = AsyncMock(return_value=mock_result)

        result = await _build_specs_from_project_integrations(session, uuid.uuid4())
        assert result == {}

    @pytest.mark.asyncio
    async def test_dispatches_adora_v3(self):
        pi = _make_project_integration(
            config={
                "menu_data": {"items": []},
                "auth": {
                    "type": "bearer",
                    "rotation": {"enabled": True, "token_url": "https://t/token"},
                },
            },
        )
        integration_record = _make_integration_record(
            client_id="real-key", client_secret="real-secret", secret_key=None
        )

        session = AsyncMock()
        # First call: ProjectIntegration query
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([pi])
        # Second call: Integration query
        int_result = MagicMock()
        int_result.scalar_one_or_none.return_value = integration_record

        session.execute = AsyncMock(side_effect=[pi_result, int_result])

        result = await _build_specs_from_project_integrations(session, uuid.uuid4())

        assert "adora" in result
        spec = result["adora"]
        assert isinstance(spec, AdoraSpec)
        assert spec.enabled is True
        assert spec.auth is not None
        assert spec.auth["rotation"]["client_id"] == "real-key"

    @pytest.mark.asyncio
    async def test_no_integration_record_passes_none_credentials(self):
        pi = _make_project_integration(
            config={"menu_data": {}},
        )

        session = AsyncMock()
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([pi])
        int_result = MagicMock()
        int_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[pi_result, int_result])

        result = await _build_specs_from_project_integrations(session, uuid.uuid4())

        assert "adora" in result


# ---------------------------------------------------------------------------
# _resolve_integration_credentials
# ---------------------------------------------------------------------------


class TestResolveIntegrationCredentials:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_integration(self):
        client_id, client_secret, parsed_secrets = (
            await _resolve_integration_credentials(None)
        )
        assert client_id is None
        assert client_secret is None
        assert parsed_secrets is None

    @pytest.mark.asyncio
    async def test_falls_back_to_integration_columns_when_no_secret_key(self):
        record = _make_integration_record(
            client_id="db-client-id",
            client_secret="db-client-secret",
            secret_key=None,
        )
        client_id, client_secret, parsed_secrets = (
            await _resolve_integration_credentials(record)
        )
        assert client_id == "db-client-id"
        assert client_secret == "db-client-secret"
        assert parsed_secrets is None

    @pytest.mark.asyncio
    @patch("services.agent_service._implementation.async_get_client_secret")
    async def test_reads_credentials_from_secret_manager(self, mock_get_secret):
        record = _make_integration_record(
            client_id="db-client-id",
            client_secret="db-client-secret",
            secret_key="SECRET_KEY",
        )
        mock_get_secret.return_value = (
            '{"client_id":"secret-client-id","client_secret":"secret-client-secret"}'
        )

        client_id, client_secret, parsed_secrets = (
            await _resolve_integration_credentials(record)
        )
        assert client_id == "secret-client-id"
        assert client_secret == "secret-client-secret"
        assert parsed_secrets is not None
        assert parsed_secrets["client_id"] == "secret-client-id"

    @pytest.mark.asyncio
    @patch("services.agent_service._implementation.async_get_client_secret")
    async def test_falls_back_to_columns_on_secret_lookup_error(self, mock_get_secret):
        record = _make_integration_record(
            client_id="db-client-id",
            client_secret="db-client-secret",
            secret_key="SECRET_KEY",
        )
        mock_get_secret.side_effect = KeyError("missing")

        client_id, client_secret, parsed_secrets = (
            await _resolve_integration_credentials(record)
        )
        assert client_id == "db-client-id"
        assert client_secret == "db-client-secret"
        assert parsed_secrets is None
