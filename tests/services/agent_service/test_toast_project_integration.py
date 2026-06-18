import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pal_agents.spec import ToastSpec

from agent import (
    AgentConfig,
    AgentMetadata,
    AgentPersona,
    KnowledgeConfig,
    LlamaIndexSettings,
    ModelConfig,
    ToolConfig,
    ToolMetadata,
    VectorStoreModality,
    VectorStoreProvider,
)
from db.tables.types import Channel
from services.agent_service import _implementation
from services.agent_service import _pal_agent_tool_registry as registry
from services.agent_service._implementation import (
    _build_specs_from_project_integrations,
)
from services.agent_service._pal_agent_tool_registry import (
    PAL_AGENT_TOOL_REGISTRY,
    _build_adora_v3_spec,
    _build_toast_v3_spec,
)


def _make_project_integration(
    *,
    tool_name: str = "toast_v3",
    store_identifier: str = "restaurant-guid-1",
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
    client_id: str = "toast-client-id",
    client_secret: str = "toast-client-secret",
    secret_key: str | None = None,
):
    record = MagicMock()
    record.id = uuid.uuid4()
    record.client_id = client_id
    record.client_secret = client_secret
    record.secret_key = secret_key
    return record


def _build_agent_config() -> AgentConfig:
    return AgentConfig(
        persona=AgentPersona(
            name="Test Agent",
            role="assistant",
            description="You are a helpful assistant.",
        ),
        model=ModelConfig(),
        knowledge=KnowledgeConfig(
            enabled=True,
            identifier="test-knowledge",
            settings=LlamaIndexSettings(
                vector_store_provider=VectorStoreProvider.PINECONE,
                vector_store_modality=VectorStoreModality.TEXT,
                index_name="test-index",
                namespace="test-namespace",
            ),
        ),
        tool=ToolConfig(
            identifiers=[],
            metadata=ToolMetadata(
                agent_id=uuid.uuid4(),
                account_id=uuid.uuid4(),
                account_name="test-account",
                user_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
            ),
        ),
        metadata=AgentMetadata(
            account_name="test-account",
            agent_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
        ),
    )


class TestBuildToastV3Spec:
    def test_hosted_checkout_delivery_only_is_allowed_config_field(self):
        assert "hosted_checkout_delivery_only" in registry._TOAST_SPEC_FIELDS

    def test_hosted_checkout_delivery_only_config_is_passed_through(self, monkeypatch):
        captured_kwargs = {}

        class CapturingToastSpec:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

        monkeypatch.setattr(registry, "ToastSpec", CapturingToastSpec)

        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "enable_hosted_checkout": True,
            "hosted_checkout_delivery_only": True,
        }

        registry._build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert captured_kwargs["enable_hosted_checkout"] is True
        assert captured_kwargs["hosted_checkout_delivery_only"] is True

    def test_hosted_checkout_delivery_only_is_omitted_when_unset(self, monkeypatch):
        captured_kwargs = {}

        class CapturingToastSpec:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

        monkeypatch.setattr(registry, "ToastSpec", CapturingToastSpec)

        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "enable_hosted_checkout": True,
        }

        registry._build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert "hosted_checkout_delivery_only" not in captured_kwargs

    def test_basic_build_uses_store_identifier_and_auto_auth(self):
        config = {
            "menu_data": {"version": "v2", "items": []},
            "takeout_dining_option_guid": "takeout-guid-1",
            "submit_orders": True,
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert isinstance(result, ToastSpec)
        assert result.enabled is True
        assert result.restaurant_guid == "restaurant-guid-1"
        assert result.takeout_dining_option_guid == "takeout-guid-1"
        assert result.submit_orders is True
        assert result.auth is not None
        assert result.auth["type"] == "bearer"
        assert result.auth["rotation"]["token_url"] == (
            "https://ws-api.toasttab.com/authentication/v1/authentication/login"
        )
        assert result.auth["rotation"]["client_id"] == "cid"
        assert result.auth["rotation"]["client_secret"] == "csecret"

    def test_auth_from_config_is_merged_with_credentials(self):
        config = {
            "menu_data": {"version": "v2", "items": []},
            "takeout_dining_option_guid": "takeout-guid-1",
            "auth": {
                "type": "bearer",
                "rotation": {
                    "enabled": True,
                    "token_url": "https://custom.toast/token",
                    "scope": "orders:read",
                },
            },
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "secret-client-id",
            "secret-client-secret",
            None,
        )

        assert result.auth is not None
        assert result.auth["rotation"]["token_url"] == "https://custom.toast/token"
        assert result.auth["rotation"]["scope"] == "orders:read"
        assert result.auth["rotation"]["client_id"] == "secret-client-id"
        assert result.auth["rotation"]["client_secret"] == "secret-client-secret"

    def test_bearer_auth_without_rotation_uses_integration_credentials(self):
        config = {
            "menu_data": {"version": "v2", "items": []},
            "takeout_dining_option_guid": "takeout-guid-1",
            "auth": {
                "type": "bearer",
            },
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "secret-client-id",
            "secret-client-secret",
            None,
        )

        assert result.auth is not None
        assert result.auth["type"] == "bearer"
        assert result.auth["rotation"]["enabled"] is True
        assert result.auth["rotation"]["token_url"] == (
            "https://ws-api.toasttab.com/authentication/v1/authentication/login"
        )
        assert result.auth["rotation"]["client_id"] == "secret-client-id"
        assert result.auth["rotation"]["client_secret"] == "secret-client-secret"

    def test_hosted_checkout_flag_is_preserved(self):
        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "enable_hosted_checkout": True,
        }
        integration_secrets = {
            "payment_client_id": "secret-payment-id",
            "payment_client_secret": "secret-payment-secret",
            "iframe_client_id": "secret-iframe-id",
            "iframe_client_secret": "secret-iframe-secret",
            "payment_iframe_secret": "ignored-secret",
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            integration_secrets,
        )

        assert result.enable_hosted_checkout is True

    def test_revenue_center_id_is_passed_through(self):
        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "revenue_center_id": "abc12345-def6-7890-abcd-ef1234567890",
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert result.revenue_center_id == "abc12345-def6-7890-abcd-ef1234567890"

    def test_revenue_center_id_defaults_to_none(self):
        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert result.revenue_center_id is None

    def test_expose_lookup_qualifiers_flag_is_preserved(self):
        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "expose_lookup_qualifiers": False,
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert result.expose_lookup_qualifiers is False

    def test_checkout_behavior_flags_are_preserved(self):
        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "tax_exempt_checks": True,
            "enable_duplicate_selection_instance_keys": True,
            "set_asap_promised_date_to_submission_time": True,
            "asap_future_prep_time_minutes": 30,
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert result.tax_exempt_checks is True
        assert result.enable_duplicate_selection_instance_keys is True
        assert result.set_asap_promised_date_to_submission_time is True
        assert result.asap_future_prep_time_minutes == 30

    def test_hosted_checkout_builds_without_embedding_credentials(self):
        config = {
            "menu_data": {"version": "v2"},
            "takeout_dining_option_guid": "takeout-guid-1",
            "enable_hosted_checkout": True,
        }

        result = _build_toast_v3_spec(
            config,
            "restaurant-guid-1",
            "cid",
            "csecret",
            None,
        )

        assert result.enable_hosted_checkout is True


class TestBuildSpecsFromProjectIntegrationsToast:
    @pytest.mark.asyncio
    async def test_dispatches_toast_v3(self):
        pi = _make_project_integration(
            config={
                "menu_data": {"version": "v2", "items": []},
                "takeout_dining_option_guid": "takeout-guid-1",
            },
        )
        integration_record = _make_integration_record(
            client_id="real-client-id",
            client_secret="real-client-secret",
            secret_key=None,
        )

        session = AsyncMock()
        pi_result = MagicMock()
        pi_result.scalars.return_value = iter([pi])
        int_result = MagicMock()
        int_result.scalar_one_or_none.return_value = integration_record
        session.execute = AsyncMock(side_effect=[pi_result, int_result])

        result = await _build_specs_from_project_integrations(session, uuid.uuid4())

        assert "toast" in result
        spec = result["toast"]
        assert isinstance(spec, ToastSpec)
        assert spec.enabled is True
        assert spec.restaurant_guid == "restaurant-guid-1"
        assert spec.takeout_dining_option_guid == "takeout-guid-1"
        assert spec.auth is not None
        assert spec.auth["rotation"]["client_id"] == "real-client-id"
        assert spec.auth["rotation"]["client_secret"] == "real-client-secret"


@pytest.mark.asyncio
async def test_construct_agent_spec_threads_toast_spec(monkeypatch):
    mock_construct_agent_config = AsyncMock(return_value=_build_agent_config())
    monkeypatch.setattr(
        _implementation,
        "construct_agent_config",
        mock_construct_agent_config,
    )
    monkeypatch.setattr(
        _implementation,
        "_build_specs_from_project_integrations",
        AsyncMock(
            return_value={
                "toast": ToastSpec(
                    enabled=True,
                    menu_data={"version": "v2", "items": []},
                    restaurant_guid="restaurant-guid-1",
                    takeout_dining_option_guid="takeout-guid-1",
                    submit_orders=True,
                )
            }
        ),
    )
    monkeypatch.setattr(
        _implementation,
        "_build_pal_tools_specs_from_project_integrations",
        AsyncMock(return_value=[]),
    )

    # Mock AgentRepositoryAsync to return agent with no language
    from unittest.mock import MagicMock

    mock_db_agent = MagicMock()
    mock_db_agent.language = None

    mock_agent_repo = AsyncMock()
    mock_agent_repo.get_agent = AsyncMock(return_value=mock_db_agent)
    monkeypatch.setattr(
        _implementation.db,
        "AgentRepositoryAsync",
        lambda session: mock_agent_repo,
    )

    spec = await _implementation.construct_agent_spec(
        session=AsyncMock(),
        agent_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        channel=Channel.SMS,
        raw_config={},
    )

    assert spec.toast.enabled is True
    assert spec.toast.restaurant_guid == "restaurant-guid-1"
    assert spec.toast.takeout_dining_option_guid == "takeout-guid-1"
    assert spec.toast.submit_orders is True


def test_registry_keeps_adora_mapping_unchanged():
    adora_entry = PAL_AGENT_TOOL_REGISTRY["adora_v3"]
    assert adora_entry.spec_field == "adora"
    assert adora_entry.builder is _build_adora_v3_spec
