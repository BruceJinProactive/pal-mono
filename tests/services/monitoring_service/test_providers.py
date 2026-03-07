"""Tests for monitoring LLM provider abstraction layer."""

from unittest.mock import MagicMock

import pytest

from services.monitoring_service._providers import (
    NATIVE_VIDEO_MODELS,
    AzureOpenAIMonitoringProvider,
    GoogleMonitoringProvider,
    MonitoringLLMConfig,
    MonitoringLLMProvider,
    _strip_additional_properties,
    create_monitoring_llm_provider,
    supports_native_video,
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
        mocker.patch(
            "services.monitoring_service._providers.AzureOpenAI",
            return_value=MagicMock(),
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
            "services.monitoring_service._providers._get_deployment_name",
            return_value="gpt-4o-deployment",
        )

        provider = create_monitoring_llm_provider()
        assert isinstance(provider, AzureOpenAIMonitoringProvider)
        assert provider.config.provider == MonitoringLLMProvider.AZURE
        assert provider.config.model == "gpt-4o"


class TestSupportsNativeVideo:
    """Tests for supports_native_video and NATIVE_VIDEO_MODELS."""

    def test_gemini_2_5_flash_supported(self):
        """gemini-2.5-flash should support native video."""
        assert (
            supports_native_video(MonitoringLLMProvider.GOOGLE, "gemini-2.5-flash")
            is True
        )

    def test_gemini_2_5_flash_in_native_video_models(self):
        """gemini-2.5-flash should be in NATIVE_VIDEO_MODELS set."""
        assert "gemini-2.5-flash" in NATIVE_VIDEO_MODELS

    def test_gemini_3_flash_preview_not_supported(self):
        """gemini-3-flash-preview should not support native video."""
        assert (
            supports_native_video(
                MonitoringLLMProvider.GOOGLE, "gemini-3-flash-preview"
            )
            is False
        )

    def test_azure_provider_never_supported(self):
        """Azure provider should never support native video regardless of model."""
        assert (
            supports_native_video(MonitoringLLMProvider.AZURE, "gemini-2.5-flash")
            is False
        )
        assert supports_native_video(MonitoringLLMProvider.AZURE, "gpt-4o") is False

    def test_unknown_model_not_supported(self):
        """Unknown models should not support native video."""
        assert (
            supports_native_video(MonitoringLLMProvider.GOOGLE, "unknown-model")
            is False
        )


class TestGoogleMonitoringProviderAnalyzeNativeVideo:
    """Tests for GoogleMonitoringProvider.analyze_native_video."""

    def test_sends_video_bytes_as_single_part(self, mocker):
        """Should send entire video as a single Part.from_bytes with correct MIME type."""
        mocker.patch(
            "services.monitoring_service._providers.get_server_secret_with_fallback",
            return_value="test-key",
        )

        mock_client = MagicMock()
        mocker.patch(
            "services.monitoring_service._providers.genai.Client",
            return_value=mock_client,
        )

        # Mock response
        mock_response = MagicMock()
        mock_response.text = '{"result": "pass", "details": "OK"}'
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50
        mock_response.usage_metadata.total_token_count = 150
        mock_client.models.generate_content.return_value = mock_response

        mock_part_from_bytes = mocker.patch(
            "services.monitoring_service._providers.Part.from_bytes",
            return_value=MagicMock(),
        )

        config = MonitoringLLMConfig(
            provider=MonitoringLLMProvider.GOOGLE, model="gemini-2.5-flash"
        )
        provider = GoogleMonitoringProvider(config)

        result = provider.analyze_native_video(
            system_instruction="Test instruction",
            analysis_task="Test task",
            reference_images=[],
            video_bytes=b"fake-video-data",
            video_mime_type="video/mp4",
        )

        assert result == {"result": "pass", "details": "OK"}

        # Verify Part.from_bytes was called with video bytes and mime type
        mock_part_from_bytes.assert_called_with(
            data=b"fake-video-data", mime_type="video/mp4"
        )

    def test_includes_reference_images(self, mocker):
        """Should include reference images alongside the video."""
        mocker.patch(
            "services.monitoring_service._providers.get_server_secret_with_fallback",
            return_value="test-key",
        )

        mock_client = MagicMock()
        mocker.patch(
            "services.monitoring_service._providers.genai.Client",
            return_value=mock_client,
        )

        mock_response = MagicMock()
        mock_response.text = '{"result": "pass", "details": "OK"}'
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        mock_part_from_bytes = mocker.patch(
            "services.monitoring_service._providers.Part.from_bytes",
            return_value=MagicMock(),
        )

        config = MonitoringLLMConfig(
            provider=MonitoringLLMProvider.GOOGLE, model="gemini-2.5-flash"
        )
        provider = GoogleMonitoringProvider(config)

        import base64

        ref_data = base64.b64encode(b"ref-image").decode()

        provider.analyze_native_video(
            system_instruction="Test",
            analysis_task="Task",
            reference_images=[{"description": "Reference", "base64_data": ref_data}],
            video_bytes=b"video-data",
        )

        # Should have calls for reference image (jpeg) and video (mp4)
        calls = mock_part_from_bytes.call_args_list
        assert len(calls) == 2
        assert calls[0] == mocker.call(data=b"ref-image", mime_type="image/jpeg")
        assert calls[1] == mocker.call(data=b"video-data", mime_type="video/mp4")

    def test_uses_structured_output_schema(self, mocker):
        """Should apply structured output schema when provided."""
        mocker.patch(
            "services.monitoring_service._providers.get_server_secret_with_fallback",
            return_value="test-key",
        )

        mock_client = MagicMock()
        mocker.patch(
            "services.monitoring_service._providers.genai.Client",
            return_value=mock_client,
        )

        mock_response = MagicMock()
        mock_response.text = '{"result": "pass"}'
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        mocker.patch(
            "services.monitoring_service._providers.Part.from_bytes",
            return_value=MagicMock(),
        )

        config = MonitoringLLMConfig(
            provider=MonitoringLLMProvider.GOOGLE, model="gemini-2.5-flash"
        )
        provider = GoogleMonitoringProvider(config)

        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "test", "strict": True, "schema": schema},
        }

        provider.analyze_native_video(
            system_instruction="Test",
            analysis_task="Task",
            reference_images=[],
            video_bytes=b"video",
            response_format=response_format,
        )

        # Verify generate_content was called with the structured schema in config
        call_kwargs = mock_client.models.generate_content.call_args
        gen_config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert gen_config is not None
        # GenerateContentConfig should carry the schema (with additionalProperties stripped)
        assert gen_config.response_schema == schema
        assert gen_config.response_mime_type == "application/json"

    def test_raises_on_invalid_json_response(self, mocker):
        """Should raise JSONDecodeError when response is not valid JSON."""
        mocker.patch(
            "services.monitoring_service._providers.get_server_secret_with_fallback",
            return_value="test-key",
        )

        mock_client = MagicMock()
        mocker.patch(
            "services.monitoring_service._providers.genai.Client",
            return_value=mock_client,
        )

        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        mocker.patch(
            "services.monitoring_service._providers.Part.from_bytes",
            return_value=MagicMock(),
        )

        config = MonitoringLLMConfig(
            provider=MonitoringLLMProvider.GOOGLE, model="gemini-2.5-flash"
        )
        provider = GoogleMonitoringProvider(config)

        import json

        with pytest.raises(json.JSONDecodeError):
            provider.analyze_native_video(
                system_instruction="Test",
                analysis_task="Task",
                reference_images=[],
                video_bytes=b"video",
            )
