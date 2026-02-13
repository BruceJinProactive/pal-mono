"""Tests for monitoring LLM provider abstraction layer."""

from unittest.mock import MagicMock

import pytest

from services.monitoring_service._providers import (
    AzureOpenAIMonitoringProvider,
    GoogleMonitoringProvider,
    MonitoringLLMConfig,
    MonitoringLLMProvider,
    _strip_additional_properties,
    create_monitoring_llm_provider,
)


class TestStripAdditionalProperties:
    """Tests for _strip_additional_properties — JSON schema cleaning."""

    def test_removes_additional_properties_at_top_level(self):
        """Should remove additionalProperties from top-level schema."""
        schema = {"type": "object", "additionalProperties": False, "properties": {}}
        result = _strip_additional_properties(schema)
        assert "additionalProperties" not in result
        assert result["type"] == "object"

    def test_removes_enum_metadata(self):
        """Should remove custom enum_metadata field."""
        schema = {"type": "string", "enum_metadata": {"colors": ["red", "green"]}}
        result = _strip_additional_properties(schema)
        assert "enum_metadata" not in result
        assert result["type"] == "string"

    def test_recursively_cleans_nested_properties(self):
        """Should recursively clean nested property schemas."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "additionalProperties": False},
                "nested": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "deep": {"type": "string", "enum_metadata": {"x": 1}}
                    },
                },
            },
        }
        result = _strip_additional_properties(schema)
        assert "additionalProperties" not in result["properties"]["name"]
        assert "additionalProperties" not in result["properties"]["nested"]
        assert (
            "enum_metadata" not in result["properties"]["nested"]["properties"]["deep"]
        )

    def test_recursively_cleans_items_in_arrays(self):
        """Should recursively clean items schema for array types."""
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"id": {"type": "integer"}},
            },
        }
        result = _strip_additional_properties(schema)
        assert "additionalProperties" not in result["items"]

    def test_cleans_anyof_composition(self):
        """Should clean schemas within anyOf composition."""
        schema = {
            "anyOf": [
                {"type": "string", "additionalProperties": False},
                {"type": "integer", "enum_metadata": {}},
            ]
        }
        result = _strip_additional_properties(schema)
        assert "additionalProperties" not in result["anyOf"][0]
        assert "enum_metadata" not in result["anyOf"][1]

    def test_cleans_allof_composition(self):
        """Should clean schemas within allOf composition."""
        schema = {
            "allOf": [
                {"type": "object", "additionalProperties": False},
            ]
        }
        result = _strip_additional_properties(schema)
        assert "additionalProperties" not in result["allOf"][0]

    def test_cleans_oneof_composition(self):
        """Should clean schemas within oneOf composition."""
        schema = {
            "oneOf": [
                {"type": "string", "enum_metadata": {"a": 1}},
            ]
        }
        result = _strip_additional_properties(schema)
        assert "enum_metadata" not in result["oneOf"][0]

    def test_non_dict_input_returns_as_is(self):
        """Should return non-dict input unchanged."""
        assert _strip_additional_properties("string") == "string"  # type: ignore[arg-type]
        assert _strip_additional_properties(42) == 42  # type: ignore[arg-type]
        assert _strip_additional_properties(None) is None  # type: ignore[arg-type]

    def test_preserves_valid_schema_keys(self):
        """Should preserve valid JSON Schema keys that are not custom fields."""
        schema = {
            "type": "object",
            "required": ["name"],
            "description": "A test schema",
            "properties": {"name": {"type": "string"}},
        }
        result = _strip_additional_properties(schema)
        assert result["type"] == "object"
        assert result["required"] == ["name"]
        assert result["description"] == "A test schema"


class TestMonitoringLLMConfig:
    """Tests for MonitoringLLMConfig — configuration defaults."""

    def test_default_config(self):
        """Should default to Azure provider with gpt-4o model."""
        config = MonitoringLLMConfig()
        assert config.provider == MonitoringLLMProvider.AZURE
        assert config.model == "gpt-4o"
        assert config.max_tokens == 2000

    def test_google_provider_default_model(self):
        """Should default to gemini-3-flash-preview for Google provider."""
        config = MonitoringLLMConfig(provider=MonitoringLLMProvider.GOOGLE)
        assert config.provider == MonitoringLLMProvider.GOOGLE
        assert config.model == "gemini-3-flash-preview"

    def test_explicit_provider_and_model(self):
        """Should use explicit provider and model when both provided."""
        config = MonitoringLLMConfig(
            provider=MonitoringLLMProvider.GOOGLE, model="gemini-2.0-flash"
        )
        assert config.provider == MonitoringLLMProvider.GOOGLE
        assert config.model == "gemini-2.0-flash"

    def test_custom_max_tokens(self):
        """Should allow custom max_tokens."""
        config = MonitoringLLMConfig(max_tokens=4000)
        assert config.max_tokens == 4000


class TestCreateMonitoringLLMProvider:
    """Tests for create_monitoring_llm_provider — factory function."""

    def test_azure_config_returns_azure_provider(self, mocker):
        """Should return AzureOpenAIMonitoringProvider for Azure config."""
        mocker.patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        )
        # Mock the AzureOpenAI client and Pin to avoid real API calls
        mocker.patch(
            "services.monitoring_service._providers.AzureOpenAI",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.monitoring_service._providers.Pin.get_from",
            return_value=None,
        )
        mocker.patch(
            "services.monitoring_service._providers._get_deployment_name",
            return_value="gpt-4o-deployment",
        )

        config = MonitoringLLMConfig(provider=MonitoringLLMProvider.AZURE)
        provider = create_monitoring_llm_provider(config)
        assert isinstance(provider, AzureOpenAIMonitoringProvider)

    def test_google_config_returns_google_provider(self, mocker):
        """Should return GoogleMonitoringProvider for Google config."""
        mocker.patch(
            "services.monitoring_service._providers.get_server_secret_with_fallback",
            return_value="test-google-key",
        )
        mocker.patch(
            "services.monitoring_service._providers.genai.Client",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.monitoring_service._providers.Pin.get_from",
            return_value=None,
        )

        config = MonitoringLLMConfig(provider=MonitoringLLMProvider.GOOGLE)
        provider = create_monitoring_llm_provider(config)
        assert isinstance(provider, GoogleMonitoringProvider)

    def test_unsupported_provider_raises_error(self):
        """Should raise ValueError for unsupported provider."""
        config = MagicMock()
        config.provider = "unsupported"

        with pytest.raises(ValueError, match="Unsupported"):
            create_monitoring_llm_provider(config)

    def test_no_config_creates_default(self, mocker):
        """Should create default Azure config when no config provided."""
        mocker.patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            },
        )
        mocker.patch(
            "services.monitoring_service._providers.AzureOpenAI",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.monitoring_service._providers.Pin.get_from",
            return_value=None,
        )
        mocker.patch(
            "services.monitoring_service._providers._get_deployment_name",
            return_value="gpt-4o-deployment",
        )

        provider = create_monitoring_llm_provider()
        assert isinstance(provider, AzureOpenAIMonitoringProvider)
        assert provider.config.provider == MonitoringLLMProvider.AZURE
        assert provider.config.model == "gpt-4o"
