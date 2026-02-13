"""Monitoring LLM Provider Abstraction Layer.

This module provides a unified interface for different LLM providers (Azure OpenAI, Google Gemini)
used in the monitoring service for vision-based analysis.
"""

from __future__ import annotations

import base64
import copy
import json
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from ddtrace._trace.pin import Pin  # type: ignore[reportPrivateUsage]
from google import genai
from google.genai.types import GenerateContentConfig, Part
from openai import AzureOpenAI

from agent.model._config import ModelOptions
from agent.model._implementation import _get_deployment_name
from utils.log import logger
from utils.secret import get_server_secret_with_fallback


def _strip_additional_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively remove 'additionalProperties' and custom fields from a JSON schema.

    Gemini doesn't support the 'additionalProperties' field or custom non-standard
    JSON Schema fields like 'enum_metadata', so we strip them from all levels.

    Args:
        schema: JSON schema dictionary

    Returns:
        Schema with 'additionalProperties' and custom fields removed at all levels
    """
    if not isinstance(schema, dict):
        return schema

    # Remove additionalProperties and custom fields at current level
    # enum_metadata is a custom field used for UI display (colors, descriptions)
    # but is not part of the JSON Schema spec and causes Gemini validation errors
    custom_fields = {"additionalProperties", "enum_metadata"}
    cleaned = {k: v for k, v in schema.items() if k not in custom_fields}

    # Recursively clean nested schemas
    for key, value in cleaned.items():
        if key == "properties" and isinstance(value, dict):
            # Clean each property schema
            cleaned[key] = {
                prop_key: _strip_additional_properties(prop_value)
                for prop_key, prop_value in value.items()
            }
        elif key == "items" and isinstance(value, dict):
            # Clean array item schema
            cleaned[key] = _strip_additional_properties(value)
        elif key in ("anyOf", "allOf", "oneOf") and isinstance(value, list):
            # Clean schemas in composition keywords
            cleaned[key] = [_strip_additional_properties(item) for item in value]
        elif isinstance(value, dict):
            # Recursively clean nested objects
            cleaned[key] = _strip_additional_properties(value)

    return cleaned


class MonitoringLLMProvider(str, Enum):
    """Supported LLM providers for monitoring service."""

    AZURE = "azure"
    GOOGLE = "google"


class MonitoringLLMConfig:
    """Configuration for monitoring LLM."""

    def __init__(
        self,
        provider: MonitoringLLMProvider | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
    ):
        """
        Initialize monitoring LLM configuration.

        Args:
            provider: LLM provider to use (defaults to "azure")
            model: Model identifier (defaults to provider default)
            max_tokens: Maximum tokens for response (default: 2000)
        """
        # Default to Azure if no provider specified
        self.provider = provider or MonitoringLLMProvider.AZURE

        # Get model or use provider default
        if model:
            self.model = model
        else:
            # Use provider-specific defaults
            if self.provider == MonitoringLLMProvider.AZURE:
                self.model = "gpt-4o"
            else:  # GOOGLE
                self.model = "gemini-3-flash-preview"

        self.max_tokens = max_tokens


class MonitoringLLMProviderBase(ABC):
    """Abstract base class for monitoring LLM providers."""

    def __init__(self, config: MonitoringLLMConfig):
        """
        Initialize provider with configuration.

        Args:
            config: Monitoring LLM configuration
        """
        self.config = config

    @abstractmethod
    def analyze_image(
        self,
        system_instruction: str,
        analysis_task: str,
        reference_images: list[dict[str, Any]],
        camera_image_base64: str,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze camera image against reference images.

        Args:
            system_instruction: System-level instruction for the LLM
            analysis_task: Specific task description
            reference_images: List of reference images with descriptions and base64 data
            camera_image_base64: Base64-encoded camera image
            response_format: Optional JSON schema for structured output

        Returns:
            dict: Analysis result containing "result" and "details" keys

        Raises:
            Exception: If LLM call fails
        """
        pass

    @abstractmethod
    def analyze_video_frames(
        self,
        system_instruction: str,
        analysis_task: str,
        reference_images: list[dict[str, Any]],
        video_frames: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze video frames extracted at regular intervals against reference images.

        Args:
            system_instruction: System-level instruction for the LLM
            analysis_task: Specific task description
            reference_images: List of reference images with descriptions and base64 data
            video_frames: List of dicts with 'base64_data' and 'timestamp_label' keys
            response_format: Optional JSON schema for structured output

        Returns:
            dict: Analysis result containing "result" and "details" keys

        Raises:
            Exception: If LLM call fails
        """
        pass


class AzureOpenAIMonitoringProvider(MonitoringLLMProviderBase):
    """Azure OpenAI provider for monitoring LLM analysis."""

    def __init__(self, config: MonitoringLLMConfig):
        """
        Initialize Azure OpenAI provider.

        Args:
            config: Monitoring LLM configuration

        Raises:
            ValueError: If Azure OpenAI credentials are not set
        """
        super().__init__(config)
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

        if not api_key or not endpoint:
            raise ValueError(
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables are required for Azure OpenAI provider"
            )

        self.client = AzureOpenAI(
            api_key=api_key, azure_endpoint=endpoint, api_version=api_version
        )

        # Disable Datadog tracing for this client (LLMObs.enable() auto-patches OpenAI)
        # This prevents monitoring LLM calls from appearing in voice agent traces
        pin = Pin.get_from(self.client)
        if pin:
            pin.remove_from(self.client)

        # Get Azure deployment name for the model
        self.deployment_name = self._get_model_deployment(config.model)

    def _get_model_deployment(self, model: str) -> str:
        """
        Get Azure OpenAI deployment name for a given model.

        Args:
            model: Model identifier (e.g., 'gpt-4o')

        Returns:
            Deployment name from environment variable

        Raises:
            ValueError: If model is not supported or deployment name is not set
        """
        # Map model names to ModelOptions enum
        model_options_map = {
            "gpt-4o": ModelOptions.GPT_4O,
        }

        model_option = model_options_map.get(model)
        if not model_option:
            raise ValueError(
                f"Unknown Azure OpenAI model '{model}'. Supported models: {list(model_options_map.keys())}"
            )

        # Use existing _get_deployment_name function from agent.model
        return _get_deployment_name(model_option)

    def analyze_image(
        self,
        system_instruction: str,
        analysis_task: str,
        reference_images: list[dict[str, Any]],
        camera_image_base64: str,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze camera image using Azure OpenAI Vision API.

        Args:
            system_instruction: System-level instruction
            analysis_task: Specific task description
            reference_images: List of dicts with 'description' and 'base64_data' keys
            camera_image_base64: Base64-encoded camera image
            response_format: Optional JSON schema for structured output

        Returns:
            dict: Analysis result from Azure OpenAI

        Raises:
            Exception: If Azure OpenAI API call fails
        """
        # Build message content (same format as OpenAI)
        message_content: list[dict[str, Any]] = [
            {"type": "text", "text": system_instruction},
            {"type": "text", "text": analysis_task},
        ]

        # Add reference images
        if reference_images:
            message_content.append({"type": "text", "text": "Reference Images:"})
            for idx, ref_img in enumerate(reference_images, 1):
                message_content.append(
                    {
                        "type": "text",
                        "text": f"Reference {idx}: {ref_img['description']}",
                    }
                )
                message_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{ref_img['base64_data']}",
                            "detail": "high",
                        },
                    }
                )

        # Add camera image
        message_content.append({"type": "text", "text": "Current Camera Image:"})
        message_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{camera_image_base64}",
                    "detail": "high",
                },
            }
        )

        # Determine response format
        openai_response_format = (
            response_format if response_format else {"type": "json_object"}
        )

        # Make Azure OpenAI API call (tracing disabled for monitoring)
        logger.info(
            f"[Monitoring LLM] Using Azure OpenAI - Model: {self.config.model}, Deployment: {self.deployment_name}, Max Tokens: {self.config.max_tokens}"
        )

        response = self.client.chat.completions.create(
            model=self.deployment_name,  # Use deployment name, not model name
            messages=[{"role": "user", "content": message_content}],  # type: ignore[arg-type]
            response_format=openai_response_format,  # type: ignore[arg-type]
            max_tokens=self.config.max_tokens,
        )

        # Log token usage
        if response.usage:
            logger.info(
                f"[Monitoring LLM] Azure OpenAI token usage - "
                f"Model: {self.config.model}, "
                f"Prompt: {response.usage.prompt_tokens}, "
                f"Completion: {response.usage.completion_tokens}, "
                f"Total: {response.usage.total_tokens}"
            )

        # Parse and return response with defensive error handling
        try:
            content = response.choices[0].message.content or "{}"
            result = json.loads(content)
            logger.info(
                f"[Monitoring LLM] Azure OpenAI analysis completed - Result: {result.get('result', 'unknown')}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(
                f"[Monitoring LLM] Failed to parse Azure OpenAI response as JSON: {e}"
            )
            logger.error(
                f"[Monitoring LLM] Raw response content: {response.choices[0].message.content}"
            )
            raise

    def analyze_video_frames(
        self,
        system_instruction: str,
        analysis_task: str,
        reference_images: list[dict[str, Any]],
        video_frames: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze video frames using Azure OpenAI Vision API.

        Args:
            system_instruction: System-level instruction
            analysis_task: Specific task description
            reference_images: List of dicts with 'description' and 'base64_data' keys
            video_frames: List of dicts with 'base64_data' and 'timestamp_label' keys
            response_format: Optional JSON schema for structured output

        Returns:
            dict: Analysis result from Azure OpenAI

        Raises:
            Exception: If Azure OpenAI API call fails
        """
        # Build message content
        message_content: list[dict[str, Any]] = [
            {"type": "text", "text": system_instruction},
            {"type": "text", "text": analysis_task},
        ]

        # Add reference images
        if reference_images:
            message_content.append({"type": "text", "text": "Reference Images:"})
            for idx, ref_img in enumerate(reference_images, 1):
                message_content.append(
                    {
                        "type": "text",
                        "text": f"Reference {idx}: {ref_img['description']}",
                    }
                )
                message_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{ref_img['base64_data']}",
                            "detail": "high",
                        },
                    }
                )

        # Add video frames with timestamp labels
        message_content.append(
            {"type": "text", "text": "Video Frames (captured at regular intervals):"}
        )
        for frame in video_frames:
            message_content.append(
                {
                    "type": "text",
                    "text": f"Frame at {frame['timestamp_label']}:",
                }
            )
            message_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame['base64_data']}",
                        "detail": "high",
                    },
                }
            )

        # Determine response format
        openai_response_format = (
            response_format if response_format else {"type": "json_object"}
        )

        logger.info(
            f"[Monitoring LLM] Using Azure OpenAI (video) - Model: {self.config.model}, "
            f"Deployment: {self.deployment_name}, Frames: {len(video_frames)}, "
            f"Max Tokens: {self.config.max_tokens}"
        )

        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=[{"role": "user", "content": message_content}],  # type: ignore[arg-type]
            response_format=openai_response_format,  # type: ignore[arg-type]
            max_tokens=self.config.max_tokens,
        )

        # Log token usage
        if response.usage:
            logger.info(
                f"[Monitoring LLM] Azure OpenAI (video) token usage - "
                f"Model: {self.config.model}, "
                f"Prompt: {response.usage.prompt_tokens}, "
                f"Completion: {response.usage.completion_tokens}, "
                f"Total: {response.usage.total_tokens}"
            )

        # Parse and return response
        try:
            content = response.choices[0].message.content or "{}"
            result = json.loads(content)
            logger.info(
                f"[Monitoring LLM] Azure OpenAI video analysis completed - Result: {result.get('result', 'unknown')}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(
                f"[Monitoring LLM] Failed to parse Azure OpenAI video response as JSON: {e}"
            )
            logger.error(
                f"[Monitoring LLM] Raw response content: {response.choices[0].message.content}"
            )
            raise


class GoogleMonitoringProvider(MonitoringLLMProviderBase):
    """Google Gemini provider for monitoring LLM analysis."""

    def __init__(self, config: MonitoringLLMConfig):
        """
        Initialize Google Gemini provider.

        Args:
            config: Monitoring LLM configuration

        Raises:
            ValueError: If GOOGLE_API_KEY is not set
        """
        super().__init__(config)
        # Fetch GOOGLE_API_KEY from AWS Secrets Manager with env fallback
        try:
            api_key = get_server_secret_with_fallback("GOOGLE_API_KEY")
        except ValueError as e:
            raise ValueError(f"Failed to retrieve Google API key: {str(e)}") from e

        self.client = genai.Client(api_key=api_key)

        # Disable Datadog tracing for this client (LLMObs.enable() auto-patches libraries)
        # This prevents monitoring LLM calls from appearing in voice agent traces
        pin = Pin.get_from(self.client)
        if pin:
            pin.remove_from(self.client)

    def analyze_image(
        self,
        system_instruction: str,
        analysis_task: str,
        reference_images: list[dict[str, Any]],
        camera_image_base64: str,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze camera image using Google Gemini Vision API.

        Args:
            system_instruction: System-level instruction
            analysis_task: Specific task description
            reference_images: List of dicts with 'description' and 'base64_data' keys
            camera_image_base64: Base64-encoded camera image
            response_format: Optional JSON schema for structured output

        Returns:
            dict: Analysis result from Gemini

        Raises:
            Exception: If Gemini API call fails
        """
        # Build content parts for multimodal input
        content_parts: list[str | Part] = [system_instruction + "\n\n" + analysis_task]

        # Add reference images with descriptions
        if reference_images:
            content_parts.append("\n**Reference Images (Expected State):**")
            for idx, ref_img in enumerate(reference_images, 1):
                content_parts.append(f"\nReference {idx}: {ref_img['description']}")
                # Decode base64 and create image part
                image_bytes = base64.b64decode(ref_img["base64_data"])
                content_parts.append(
                    Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                )

        # Add camera image
        content_parts.append(
            "\n**Current Camera Image (To Be Analyzed):**\nPlease compare this image against the reference images above and evaluate based on the analysis task."
        )
        camera_image_bytes = base64.b64decode(camera_image_base64)
        content_parts.append(
            Part.from_bytes(data=camera_image_bytes, mime_type="image/jpeg")
        )

        # Make Gemini API call (tracing disabled for monitoring)
        logger.info(
            f"[Monitoring LLM] Using Google Gemini - Model: {self.config.model}, Max Tokens: {self.config.max_tokens}"
        )

        # Configure generation with JSON schema support
        generation_config_params = {
            "max_output_tokens": self.config.max_tokens,
            "temperature": 0.0,  # Deterministic for monitoring
            "response_mime_type": "application/json",
        }

        # Gemini supports native JSON schema via response_schema parameter
        # This is similar to OpenAI's structured outputs
        if response_format:
            # Handle OpenAI-style structured output format
            if isinstance(response_format, dict) and "type" in response_format:
                # OpenAI format: {"type": "json_schema", "json_schema": {...}}
                if response_format.get("type") == "json_schema":
                    schema = response_format.get("json_schema", {}).get("schema")
                    if schema:
                        # Gemini doesn't support additionalProperties, so remove it recursively
                        # Create a deep copy to avoid modifying the original schema
                        gemini_schema = copy.deepcopy(schema)
                        gemini_schema = _strip_additional_properties(gemini_schema)
                        generation_config_params["response_schema"] = gemini_schema
                        logger.info(
                            "[Monitoring LLM] Using structured output with native Gemini JSON schema"
                        )
                    else:
                        # No valid schema found in json_schema format
                        content_parts.append(
                            '\nYou must respond with valid JSON containing "result" (pass/fail/error) and "details" keys.'
                        )
                        logger.warning(
                            "[Monitoring LLM] json_schema type specified but no schema found, falling back to prompt instructions"
                        )
                else:
                    # Plain JSON object mode - add instruction to content
                    content_parts.append(
                        '\nYou must respond with valid JSON containing "result" (pass/fail/error) and "details" keys.'
                    )
                    logger.info(
                        "[Monitoring LLM] Using JSON object mode with prompt instructions"
                    )
            else:
                # Direct schema provided - also strip additionalProperties
                cleaned_schema = copy.deepcopy(response_format)
                cleaned_schema = _strip_additional_properties(cleaned_schema)
                generation_config_params["response_schema"] = cleaned_schema
                logger.info(
                    "[Monitoring LLM] Using structured output with direct schema"
                )
        else:
            # Default: instruct for standard monitoring response format
            content_parts.append(
                '\nYou must respond with valid JSON containing "result" (pass/fail/error) and "details" keys.'
            )
            logger.info("[Monitoring LLM] Using default JSON response format")

        generation_config = GenerateContentConfig(**generation_config_params)

        response = self.client.models.generate_content(
            model=self.config.model,
            contents=content_parts,  # type: ignore[arg-type]
            config=generation_config,
        )

        # Log token usage
        if response.usage_metadata:
            logger.info(
                f"[Monitoring LLM] Gemini token usage - "
                f"Model: {self.config.model}, "
                f"Prompt: {response.usage_metadata.prompt_token_count}, "
                f"Completion: {response.usage_metadata.candidates_token_count}, "
                f"Total: {response.usage_metadata.total_token_count}"
            )

        # Parse and return response with defensive error handling
        try:
            result = json.loads(response.text or "{}")
            logger.info(
                f"[Monitoring LLM] Gemini analysis completed - Result: {result.get('result', 'unknown')}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(
                f"[Monitoring LLM] Failed to parse Gemini response as JSON: {e}"
            )
            logger.error(f"[Monitoring LLM] Raw response text: {response.text}")
            raise

    def analyze_video_frames(
        self,
        system_instruction: str,
        analysis_task: str,
        reference_images: list[dict[str, Any]],
        video_frames: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze video frames using Google Gemini Vision API.

        Args:
            system_instruction: System-level instruction
            analysis_task: Specific task description
            reference_images: List of dicts with 'description' and 'base64_data' keys
            video_frames: List of dicts with 'base64_data' and 'timestamp_label' keys
            response_format: Optional JSON schema for structured output

        Returns:
            dict: Analysis result from Gemini

        Raises:
            Exception: If Gemini API call fails
        """
        # Build content parts for multimodal input
        content_parts: list[str | Part] = [system_instruction + "\n\n" + analysis_task]

        # Add reference images with descriptions
        if reference_images:
            content_parts.append("\n**Reference Images (Expected State):**")
            for idx, ref_img in enumerate(reference_images, 1):
                content_parts.append(f"\nReference {idx}: {ref_img['description']}")
                image_bytes = base64.b64decode(ref_img["base64_data"])
                content_parts.append(
                    Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                )

        # Add video frames with timestamp labels
        content_parts.append(
            "\n**Video Frames (captured at regular intervals):**\nPlease analyze these frames from the monitoring camera and evaluate based on the analysis task."
        )
        for frame in video_frames:
            content_parts.append(f"\nFrame at {frame['timestamp_label']}:")
            frame_bytes = base64.b64decode(frame["base64_data"])
            content_parts.append(
                Part.from_bytes(data=frame_bytes, mime_type="image/jpeg")
            )

        logger.info(
            f"[Monitoring LLM] Using Google Gemini (video) - Model: {self.config.model}, "
            f"Frames: {len(video_frames)}, Max Tokens: {self.config.max_tokens}"
        )

        # Configure generation with JSON schema support
        generation_config_params = {
            "max_output_tokens": self.config.max_tokens,
            "temperature": 0.0,
            "response_mime_type": "application/json",
        }

        if response_format:
            if isinstance(response_format, dict) and "type" in response_format:
                if response_format.get("type") == "json_schema":
                    schema = response_format.get("json_schema", {}).get("schema")
                    if schema:
                        gemini_schema = copy.deepcopy(schema)
                        gemini_schema = _strip_additional_properties(gemini_schema)
                        generation_config_params["response_schema"] = gemini_schema
                        logger.info(
                            "[Monitoring LLM] Using structured output with native Gemini JSON schema (video)"
                        )
                    else:
                        content_parts.append(
                            '\nYou must respond with valid JSON containing "result" (pass/fail/error) and "details" keys.'
                        )
                        logger.warning(
                            "[Monitoring LLM] json_schema type specified but no schema found, falling back to prompt instructions (video)"
                        )
                else:
                    content_parts.append(
                        '\nYou must respond with valid JSON containing "result" (pass/fail/error) and "details" keys.'
                    )
                    logger.info(
                        "[Monitoring LLM] Using JSON object mode with prompt instructions (video)"
                    )
            else:
                cleaned_schema = copy.deepcopy(response_format)
                cleaned_schema = _strip_additional_properties(cleaned_schema)
                generation_config_params["response_schema"] = cleaned_schema
                logger.info(
                    "[Monitoring LLM] Using structured output with direct schema (video)"
                )
        else:
            content_parts.append(
                '\nYou must respond with valid JSON containing "result" (pass/fail/error) and "details" keys.'
            )
            logger.info("[Monitoring LLM] Using default JSON response format (video)")

        generation_config = GenerateContentConfig(**generation_config_params)

        response = self.client.models.generate_content(
            model=self.config.model,
            contents=content_parts,  # type: ignore[arg-type]
            config=generation_config,
        )

        # Log token usage
        if response.usage_metadata:
            logger.info(
                f"[Monitoring LLM] Gemini (video) token usage - "
                f"Model: {self.config.model}, "
                f"Prompt: {response.usage_metadata.prompt_token_count}, "
                f"Completion: {response.usage_metadata.candidates_token_count}, "
                f"Total: {response.usage_metadata.total_token_count}"
            )

        # Parse and return response
        try:
            result = json.loads(response.text or "{}")
            logger.info(
                f"[Monitoring LLM] Gemini video analysis completed - Result: {result.get('result', 'unknown')}"
            )
            return result
        except json.JSONDecodeError as e:
            logger.error(
                f"[Monitoring LLM] Failed to parse Gemini video response as JSON: {e}"
            )
            logger.error(f"[Monitoring LLM] Raw response text: {response.text}")
            raise


def create_monitoring_llm_provider(
    config: MonitoringLLMConfig | None = None,
) -> MonitoringLLMProviderBase:
    """
    Factory function to create the appropriate monitoring LLM provider.

    Args:
        config: Optional monitoring LLM configuration (defaults to env vars)

    Returns:
        MonitoringLLMProviderBase: Instantiated provider

    Raises:
        ValueError: If provider is not supported
    """
    if config is None:
        config = MonitoringLLMConfig()

    provider_map = {
        MonitoringLLMProvider.AZURE: AzureOpenAIMonitoringProvider,
        MonitoringLLMProvider.GOOGLE: GoogleMonitoringProvider,
    }

    provider_class = provider_map.get(config.provider)
    if not provider_class:
        raise ValueError(f"Unsupported monitoring LLM provider: {config.provider}")

    logger.info(
        f"Creating monitoring LLM provider: {config.provider.value} with model {config.model}"
    )
    return provider_class(config)
