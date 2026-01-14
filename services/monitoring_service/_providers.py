"""Monitoring LLM Provider Abstraction Layer.

This module provides a unified interface for different LLM providers (Azure OpenAI, Google Gemini)
used in the monitoring service for vision-based analysis.
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from ddtrace.trace import tracer
from google import genai
from google.genai.types import GenerateContentConfig, Part
from openai import AzureOpenAI

from utils.log import logger


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
            provider: LLM provider to use (defaults to env var MONITORING_LLM_PROVIDER or "azure")
            model: Model identifier (defaults to env var MONITORING_LLM_MODEL or provider default)
            max_tokens: Maximum tokens for response (default: 2000)
        """
        # Get provider from env or default to azure
        provider_str = os.getenv("MONITORING_LLM_PROVIDER", "azure")
        self.provider = provider or MonitoringLLMProvider(provider_str.lower())

        # Get model from env or use provider default
        model_env = os.getenv("MONITORING_LLM_MODEL")
        if model:
            self.model = model
        elif model_env:
            self.model = model_env
        else:
            # Default models for each provider
            if self.provider == MonitoringLLMProvider.AZURE:
                self.model = "gpt-4o"
            else:  # GOOGLE
                # Default to Gemini 3 Flash Preview for best speed/cost balance
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

        # Make Azure OpenAI API call with tracing
        logger.info(
            f"[Monitoring LLM] Using Azure OpenAI - Model: {self.config.model}, Max Tokens: {self.config.max_tokens}"
        )
        with tracer.trace(
            "monitoring.vision_analysis",
            service="pal-mono-monitoring",
            resource="azure.openai.vision.analysis",
        ) as span:
            span.set_tag("monitoring.model", self.config.model)
            span.set_tag("monitoring.provider", "azure")

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": message_content}],  # type: ignore[arg-type]
                response_format=openai_response_format,  # type: ignore[arg-type]
                max_tokens=self.config.max_tokens,
            )

        # Parse and return response
        result = json.loads(response.choices[0].message.content or "{}")
        logger.info(
            f"[Monitoring LLM] Azure OpenAI analysis completed - Result: {result.get('result', 'unknown')}"
        )
        return result


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
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required for Google Gemini provider"
            )
        self.client = genai.Client(api_key=api_key)

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

        # Make Gemini API call with tracing
        logger.info(
            f"[Monitoring LLM] Using Google Gemini - Model: {self.config.model}, Max Tokens: {self.config.max_tokens}"
        )
        with tracer.trace(
            "monitoring.vision_analysis",
            service="pal-mono-monitoring",
            resource="gemini.vision.analysis",
        ) as span:
            span.set_tag("monitoring.model", self.config.model)
            span.set_tag("monitoring.provider", "google")

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
                            generation_config_params["response_schema"] = schema
                            logger.info(
                                "[Monitoring LLM] Using structured output with native Gemini JSON schema"
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
                    # Direct schema provided
                    generation_config_params["response_schema"] = response_format
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

        # Parse and return response
        result = json.loads(response.text or "{}")
        logger.info(
            f"[Monitoring LLM] Gemini analysis completed - Result: {result.get('result', 'unknown')}"
        )
        return result


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
