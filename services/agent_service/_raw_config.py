from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from jinja2.sandbox import SandboxedEnvironment
from pydantic import ValidationError

import db
from agent import (
    AgentConfig,
    AgentMetadata,
    AgentPersona,
    FeatureConfig,
    KnowledgeConfig,
    KnowledgeProvider,
    LlamaIndexSettings,
    MemoryConfig,
    ModelConfig,
    ToolConfig,
    ToolIdentifier,
    ToolMetadata,
    TranscriberConfig,
    VoiceDecoderConfig,
)
from agent.config import (
    BackgroundSpeechDenoisingPlan,
    MultilingualSquadConfig,
    StartSpeakingPlan,
    VoiceConfig,
)
from agent.knowledge import KnowledgeConfigSettings
from agent.model import ModelProvider
from api.routes.integrations.vapi._constants import DEFAULT_MULTILINGUAL_SQUAD_CONFIG
from db.tables.accounts import BusinessIndustry
from db.tables.types import AgentType, Channel, TargetTier
from services.integration_service.schema import IntegrationDetail
from services.prompt_service.prompts import prompt_factory
from utils.log import logger


class RawConfig:
    def __init__(
        self,
        agent: db.Agent,
        project: db.Project,
        account: db.Account,
        user_id: UUID,
        conversation_id: UUID,
        channel: Channel,
        integration: IntegrationDetail | None = None,
        sender_identifier: str | None = None,
        project_integrations: Sequence[db.ProjectIntegration] | None = None,
    ):
        self.agent = agent
        self.project = project
        self.account = account
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.channel = channel
        self.integration = integration
        self.sender_identifier = sender_identifier
        self.project_integrations = list(project_integrations or [])

    def build(self) -> AgentConfig:
        try:
            memory_enabled = self.agent.raw_config.get("memory_enabled", True)
            filler_words_config = self.agent.filler_words or {}

            return AgentConfig(
                persona=self._get_agent_persona(self.channel),
                model=self._get_agent_model_config(),
                memory=MemoryConfig(
                    enabled=memory_enabled,
                    identifier=self.account.name,
                    instruction="Don't remember the user's gender.",
                ),
                knowledge=self._get_agent_knowledge(),
                tool=self._get_agent_tools(),
                feature_config=FeatureConfig(
                    chat_filler_words_percentage=filler_words_config.get(
                        "chat_filler_words_percentage", 80
                    ),
                    tool_calling_filler_words_percentage=filler_words_config.get(
                        "tool_calling_filler_words_percentage", 80
                    ),
                ),
                metadata=AgentMetadata(
                    account_name=self.account.name,
                    agent_id=str(self.agent.id),
                    user_id=str(self.user_id),
                    session_id=str(self.conversation_id),
                ),
                additional_context=self._get_additional_context(),
                voice_config=VoiceConfig(
                    enabled=self.agent.raw_config.get(
                        "vapi_voice_config_enabled", False
                    ),
                    greeting_message=self._render_greeting_message(),
                    voice_id=self.agent.voice_id,
                    speech_rate=self.agent.speech_rate,
                    background_noise=self.agent.raw_config.get(
                        "background_sound",
                        "office" if self.agent.background_noise else "off",
                    ),
                    background_speech_denoising_plan=self._get_background_speech_denoising_plan(),
                    language=self.agent.language,
                    tool_calling_filler_words=self.agent.raw_config.get(
                        "tool_calling_filler_words", {}
                    ),
                    chat_filler_words=self.agent.raw_config.get(
                        "chat_filler_words", {}
                    ),
                    tool_calling_filler_words_percentage=self.agent.raw_config.get(
                        "tool_calling_filler_words_percentage", 100
                    ),
                    chat_filler_words_percentage=self.agent.raw_config.get(
                        "chat_filler_words_percentage", 100
                    ),
                    voice_decoder=self._get_voice_decoder_config(),
                    transcriber=self._get_transcriber_config(),
                    start_speaking_plan=self._get_start_speaking_plan(),
                ),
                multiling_squad_config=self._get_multilingual_squad_config(),
            )
        except ValueError as e:
            raise ValueError(f"Invalid RawConfig: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to convert to AgentConfig: {e}") from e

    @staticmethod
    def _coerce_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized in {"true", "1", "yes", "y", "on"}
        if value is None:
            return False
        return bool(value)

    def _get_multilingual_squad_config(self) -> MultilingualSquadConfig | None:
        """
        Get the multilingual squad configuration.

        This method handles three cases for the 'multilingual_squad_config' value:
        1. A boolean `True`: Returns the default squad configuration.
        2. A dictionary: Validates and returns the custom squad configuration.
        3. `False`, `None`, or invalid: Returns `None`.
        """
        raw_config = self.agent.raw_config.get("multilingual_squad_config")

        config_to_validate = None
        if raw_config is True:
            # Use the default configuration if the flag is True
            config_to_validate = DEFAULT_MULTILINGUAL_SQUAD_CONFIG
        elif isinstance(raw_config, dict):
            # Use the provided dictionary for custom configuration
            config_to_validate = raw_config

        if config_to_validate is None:
            # Handles cases where the config is None, False, or an invalid type
            return None

        try:
            # Transform snake_case keys to match Pydantic field expectations
            transformed_config = self._transform_multilingual_config(config_to_validate)
            # Validate the transformed configuration
            return MultilingualSquadConfig.model_validate(transformed_config)
        except ValidationError as e:
            logger.error(
                "Invalid multilingual squad config",
                extra={"agent_id": self.agent.id, "error": str(e)},
            )
            # Fallback to None if validation fails
            return None

    def _snake_to_camel(self, snake_str: str) -> str:
        """Convert snake_case string to camelCase."""
        components = snake_str.split("_")
        return components[0] + "".join(word.capitalize() for word in components[1:])

    def _transform_multilingual_config(self, config: dict) -> dict:
        """
        Transform raw API configuration snake_case keys to camelCase field names.

        Automatically converts snake_case keys to camelCase, with special handling for 'assistant_name' -> 'name'.
        """

        def _transform_assistant_keys(assistant_config: dict) -> dict:
            """Transform snake_case keys to camelCase field names."""
            transformed = {}

            for key, value in assistant_config.items():
                # Special case: assistant_name maps to 'name' field in VAPIAssistant
                if key == "assistant_name":
                    transformed["name"] = value
                # Convert other snake_case keys to camelCase
                elif "_" in key:
                    camel_key = self._snake_to_camel(key)
                    transformed[camel_key] = value
                # Keep keys that are already in the correct format
                else:
                    transformed[key] = value

            return transformed

        # Apply field mapping to all assistant configurations
        transformed_config = {}

        if "triage_assistant" in config:
            transformed_config["triage_assistant"] = _transform_assistant_keys(
                config["triage_assistant"]
            )

        if "language_assistants" in config:
            transformed_config["language_assistants"] = {}
            for language, assistant_config in config["language_assistants"].items():
                transformed_config["language_assistants"][language] = (
                    _transform_assistant_keys(assistant_config)
                )

        return transformed_config

    def _get_agent_persona(self, channel: Channel) -> AgentPersona:
        # Extract the persona section of the raw config for voice_id and model_mode
        raw_persona = self.agent.raw_config.get("persona", {})

        # Always use dynamic prompt behavior
        name = self.agent.name or ""
        role = self.agent.agent_type or ""
        system_prompt = self._build_agent_prompt(channel)
        voice_id = raw_persona.get("voice_id") or None
        model_mode = raw_persona.get("model_mode") or None

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
            voice_id=voice_id,
            model_mode=model_mode,
        )

    def _get_agent_knowledge(self) -> KnowledgeConfig:
        # Extract the knowledge section of the raw config
        raw_knowledge = self.agent.raw_config.get("knowledge")

        if not raw_knowledge:
            raw_knowledge = self.project.raw_config.get("knowledge")

        if raw_knowledge:
            provider = self._get_knowledge_provider(raw_knowledge)

            if provider == KnowledgeProvider.LLAMAINDEX:
                # Use the identifier, provider, settings from the knowledge section
                identifier = raw_knowledge.get("identifier")
                if identifier is None:
                    raise ValueError(
                        "'knowledge.identifier' is not provided in 'agent.raw_config'."
                    )

                settings = raw_knowledge.get("settings")
                self._validate_settings(provider, settings)
                # Enable by default
                enable_knowledge = raw_knowledge.get("enabled", True)
                logger.debug(f"Knowledge enabled: {enable_knowledge}")

                return KnowledgeConfig(
                    enabled=enable_knowledge,
                    provider=provider,
                    identifier=identifier,
                    settings=settings,
                )
        return KnowledgeConfig(enabled=False)

    def _get_project_tools_override(self) -> dict[str, dict]:
        raw_config = self.project.raw_config or {}
        tools = raw_config.get("tools", {})
        identifiers = tools.get("identifiers", [])

        result = {}
        for identifier in identifiers:
            if not isinstance(identifier, dict) or "tool_name" not in identifier:
                raise ValueError(
                    "Each tool identifier must be a dict with 'tool_name' key"
                )
            tool_name = identifier["tool_name"]
            if tool_name in result:
                raise ValueError(
                    f"Duplicate tool f{tool_name} in project.raw_config.tools!"
                )
            result[tool_name] = identifier

        return result

    def _get_project_integration_tools(self) -> List[Tuple[str, Dict[str, Any], bool]]:
        tools: List[Tuple[str, Dict[str, Any], bool]] = []

        sorted_integrations = sorted(
            self.project_integrations,
            key=lambda integration: (integration.created_at, integration.id),
        )

        for integration in sorted_integrations:
            tool_name = integration.tool_name
            if not tool_name:
                continue

            config_payload: Dict[str, Any] = integration.config or {}
            if not isinstance(config_payload, dict):
                raise ValueError(
                    "Project integration config must be a dict for tool entries."
                )

            config_copy: Dict[str, Any] = dict(config_payload)
            access_metadata = self._coerce_bool(
                config_copy.pop("access_metadata", False)
            )

            nested_args = config_copy.pop("tool_args", None)
            if nested_args is not None:
                if not isinstance(nested_args, dict):
                    raise ValueError(
                        f"tool_args must be a dict for project integration tool {tool_name}."
                    )
                config_copy = {**config_copy, **nested_args}

            tools.append((tool_name, config_copy, access_metadata))

        return tools

    def _populate_vapi_tool_args(self, tool_args: dict) -> dict:
        """
        Populate VAPI tool arguments with transfer settings from project columns.

        Auto-populates 'transfer_message' and 'destination_number' from project fields
        if the respective project fields are not empty. Overwrites existing values.

        Args:
            tool_args: Existing tool arguments dictionary

        Returns:
            Updated tool arguments with project transfer settings
        """
        updated_args = tool_args.copy()
        # Check if both transfer fields are populated in the project
        has_transfer_phone = self.project.transfer_phone_number
        has_transfer_message = self.project.transfer_message

        # auto-populate if fields are not empty
        if has_transfer_message:
            updated_args["transfer_message"] = self.project.transfer_message
        if has_transfer_phone:
            updated_args["destination_number"] = self.project.transfer_phone_number

        return updated_args

    def _get_agent_tools(self) -> ToolConfig:
        # Extract customer phone from sender_identifier based on channel type
        customer_phone = None
        if self.sender_identifier:
            is_phone_channel = self.channel and self.channel.value.lower() in [
                "sms",
                "voice",
                "whatsapp",
            ]
            if is_phone_channel:
                customer_phone = self.sender_identifier

        metadata = ToolMetadata(
            agent_id=self.agent.id,
            account_id=self.account.id,
            account_name=self.account.name,
            user_id=self.user_id,
            session_id=self.conversation_id,
            project_id=self.project.id,
            timezone=self.project.timezone,
            customer_phone=customer_phone,
        )

        raw_tools: Dict[str, Any] = self.agent.raw_config.get("tools", {})
        raw_identifiers: List[Dict[str, Any]] = raw_tools.get("identifiers", []) or []
        if not isinstance(raw_identifiers, list):
            raise ValueError("'identifiers' should be a list.")

        project_tool_overrides = self._get_project_tools_override()
        integration_tool_entries = self._get_project_integration_tools()

        tool_order: List[str] = []

        class _MergedToolEntry(TypedDict):
            args: Dict[str, Any]
            access_metadata: bool

        merged_tools: Dict[str, _MergedToolEntry] = {}

        def _ensure_dict(value: object) -> Dict[str, Any]:
            if not isinstance(value, dict):
                raise ValueError("'tool_args' should be a dict.")
            return dict(value)

        def _set_tool(
            tool_name: str, args: Dict[str, Any], access_metadata: object
        ) -> None:
            if not tool_name:
                raise ValueError("tool_name cannot be empty.")
            if tool_name not in merged_tools:
                tool_order.append(tool_name)
            merged_tools[tool_name] = _MergedToolEntry(
                args=dict(args),
                access_metadata=self._coerce_bool(access_metadata),
            )

        for raw_tool in raw_identifiers:
            if not isinstance(raw_tool, dict):
                raise ValueError("'identifiers' should be a list of dict.")

            tool_name = str(raw_tool.get("tool_name", "") or "")
            tool_args: Dict[str, Any] = _ensure_dict(
                raw_tool.get("tool_args", {}) or {}
            )
            access_metadata = raw_tool.get("access_metadata", False)

            _set_tool(tool_name, tool_args, access_metadata)

        for tool_name, overrides in project_tool_overrides.items():
            override_args_raw = overrides.get("tool_args", {}) or {}
            override_args: Dict[str, Any] = _ensure_dict(override_args_raw)
            override_access_metadata = overrides.get("access_metadata", None)

            if tool_name in merged_tools:
                existing_args: Dict[str, Any] = merged_tools[tool_name]["args"]
                merged_args: Dict[str, Any] = {**existing_args, **override_args}
                merged_tools[tool_name]["args"] = merged_args
                if override_access_metadata is not None:
                    merged_tools[tool_name]["access_metadata"] = self._coerce_bool(
                        override_access_metadata
                    )
            else:
                _set_tool(
                    tool_name,
                    dict(override_args),
                    (
                        override_access_metadata
                        if override_access_metadata is not None
                        else False
                    ),
                )

        # Apply ProjectIntegration-provided tools
        for tool_name, tool_args, access_metadata in integration_tool_entries:
            _set_tool(tool_name, tool_args, access_metadata)

        final_identifiers: List[ToolIdentifier] = []

        for tool_name in tool_order:
            entry = merged_tools[tool_name]
            tool_args: Dict[str, Any] = dict(entry["args"])

            if tool_name == "vapi_tool":
                tool_args = self._populate_vapi_tool_args(tool_args)

            final_identifiers.append(
                ToolIdentifier(
                    tool_name=tool_name,
                    args=tool_args,
                    access_metadata=bool(entry["access_metadata"]),
                )
            )

        return ToolConfig(identifiers=final_identifiers, metadata=metadata)

    def _get_agent_model_config(self) -> ModelConfig:
        raw_model = self.agent.raw_config.get("model", {})
        provider = raw_model.get("provider") or ModelProvider.OPENAI
        identifier = raw_model.get("identifier") or "gpt-4o"

        return ModelConfig(provider=provider, identifier=identifier)

    def _build_agent_prompt(self, channel: Channel) -> str:
        def build_section(title, info_list) -> list[str]:
            blocks = [title]
            for header, content in info_list:
                if content:
                    blocks.extend([header, content])
            # add newline to the end for better formatting
            blocks.extend("\n")
            if len(blocks) <= 2:
                # if blocks does not contain any content, then clear everything
                blocks = []
            return blocks

        brand_info_list = self._get_brand_info()
        agent_info_list = self._get_agent_info(channel)
        store_info_list = self._get_store_info()

        sections = [self._build_agent_introduction()]
        sections.extend(build_section("# Brand Information", brand_info_list))
        sections.extend(build_section("# Agent Information", agent_info_list))
        sections.extend(build_section("# Store Information", store_info_list))
        return "\n".join(sections)

    def _build_agent_introduction(self):
        agent_name = self.agent.name or "an AI agent"
        account_name = self.account.display_name or "the business"

        if self.account.industry == BusinessIndustry.FOOD_BEVERAGE:
            intro = "Your job is to help the customer with questions about the restaurant and menu."
        else:
            intro = "Your job is to help the customer with questions about the business and product & services we offer."
        return f"You are {agent_name} from {account_name}. {intro}"

    def _get_brand_info(self):
        return [
            ("## Description", self.account.business_description),
            ("## F.A.Q.", self.account.business_faq),
            ("## Catalog", self.account.business_catalog),
            ("## Current Promotions", self.account.business_promotions),
            ("## Others", self.account.business_others),
        ]

    def _get_agent_info(self, channel: Channel):
        # default to premium tier for now.
        info_list = prompt_factory.build(
            channel,
            self.agent.agent_type,
            TargetTier.t2,
            self.integration.provider if self.integration else None,
            self.agent.id,
        )

        if self.agent.communication_style:
            info_list.append(
                ("## Custom Communication Style", self.agent.communication_style)
            )
        if self.agent.interaction_guidelines:
            info_list.append(
                ("## Custom Interaction Guideline", self.agent.interaction_guidelines)
            )
        return info_list

    def _get_store_info(self):
        return [
            ("## Store Address", self.project.address),
            ("## Store Hours", self.project.store_hours),
            (
                "## Custom Service Instruction",
                self.project.service_instruction
                or self._get_default_service_instruction(),
            ),
            ("## Store Product & Menu", self.project.product_info),
        ]

    def _get_default_service_instruction(self) -> str:
        agent_type = self.agent.agent_type
        if agent_type == AgentType.ordering:
            return (
                "Help with answering customer questions as well as taking orders "
                "for pick up only, delivery is not supported."
            )
        return (
            "Help with answering customer questions as much as possible "
            "but don't take any orders."
        )

    def _get_additional_context(self) -> str:
        additional_context = ""

        timezone = self.project.timezone
        if not timezone and self.project.raw_config:
            timezone = self.project.raw_config.get("timezone")

        if timezone:
            # TODO: Once timezone PR is merged on Agno's side we can remove this
            # logic and use add_datetime_to_instructions + timezone_identifier instead
            try:
                tz = ZoneInfo(timezone)
                time = datetime.now(tz)
                formatted_time = time.strftime("%A, %Y-%m-%d %H:%M:%S %Z")

                additional_context += f"The current time is {formatted_time}."
            except Exception:
                raise ValueError(f"Timezone '{timezone}' is invalid.")

        raw_knowledge = self.agent.raw_config.get("knowledge")
        if raw_knowledge:
            provider = self._get_knowledge_provider(raw_knowledge)
            if provider == KnowledgeProvider.KNOWLEDGE_CONFIG:
                settings = raw_knowledge.get("settings")
                self._validate_settings(provider, settings)

                additional_context += f"""
                --- MENU START ---
                {settings["content"]}
                --- MENU END ---
                """

        return additional_context

    def _get_background_speech_denoising_plan(
        self,
    ) -> BackgroundSpeechDenoisingPlan | None:
        """Get background speech denoising plan with smart denoising enabled by default."""
        config = self.agent.raw_config.get("background_speech_denoising_plan")

        # Use provided config or default to smart denoising enabled
        config = config or {"smartDenoisingPlan": {"enabled": True}}

        try:
            return BackgroundSpeechDenoisingPlan.model_validate(config)
        except ValidationError as e:
            logger.warning(f"Invalid background speech denoising plan: {e}")
            return None

    def _get_knowledge_provider(self, raw_knowledge) -> Optional[KnowledgeProvider]:
        raw_provider = raw_knowledge.get("provider")

        if not raw_provider:
            raise ValueError(
                "'knowledge.provider' is not provided in 'agent.raw_config'."
            )

        provider = KnowledgeProvider(raw_provider)
        if provider not in KnowledgeProvider:
            raise ValueError(
                "'knowledge.provider' is not valid."
                f"Supported providers: {KnowledgeProvider}"
            )

        return provider

    def _validate_settings(self, provider: KnowledgeProvider, settings):
        if settings is None:
            raise ValueError(
                "'knowledge.settings' is not provided in 'agent.raw_config'."
            )

        if provider == KnowledgeProvider.LLAMAINDEX:
            # Validate that the knowledge config settings are valid for llamaindex provider
            try:
                LlamaIndexSettings.model_validate(settings)
            except ValidationError as e:
                raise ValueError(
                    "Invalid KnowledgeConfig settings for provider 'LlamaIndex'."
                ) from e
        elif provider == KnowledgeProvider.KNOWLEDGE_CONFIG:
            try:
                KnowledgeConfigSettings.model_validate(settings)
            except ValidationError as e:
                raise ValueError(
                    "Invalid KnowledgeConfig settings for provider 'KnowledgeConfig'."
                ) from e

    def _render_greeting_message(self) -> str:
        """Render the greeting message using Jinja2 sandboxed template with agent, project, and account context."""
        if not self.agent.greeting_message:
            return ""

        try:
            env = SandboxedEnvironment()
            template = env.from_string(self.agent.greeting_message)
            return template.render(
                agent=self.agent, project=self.project, account=self.account
            )
        except Exception as e:
            logger.warning(
                f"Failed to render greeting message template: {e}. Using original message.",
                extra={
                    "agent_id": self.agent.id,
                    "error": str(e),
                },
            )
            # Fallback to original message if template rendering fails
            return self.agent.greeting_message

    def _get_transcriber_config(self) -> Optional[TranscriberConfig]:
        transcriber_raw = self.agent.raw_config.get("transcriber")
        if not transcriber_raw:
            return None

        try:
            return TranscriberConfig.model_validate(transcriber_raw)
        except ValidationError as e:
            logger.warning(
                f"Invalid transcriber config in agent.raw_config: {e}",
                extra={"agent_id": self.agent.id},
            )
            return None

    def _get_voice_decoder_config(self) -> Optional[VoiceDecoderConfig]:
        voice_decoder_raw = self.agent.raw_config.get("voice_decoder")
        if not voice_decoder_raw:
            return None

        try:
            return VoiceDecoderConfig.model_validate(voice_decoder_raw)
        except ValidationError as e:
            logger.warning(
                f"Invalid voice_decoder config in agent.raw_config: {e}",
                extra={"agent_id": self.agent.id},
            )
            return None

    def _get_start_speaking_plan(self) -> Optional[StartSpeakingPlan]:
        """
        Get start speaking plan configuration from agent raw_config.
        """
        start_speaking_raw = self.agent.raw_config.get("start_speaking_plan")
        if not start_speaking_raw:
            return None

        try:
            return StartSpeakingPlan.model_validate(start_speaking_raw)
        except ValidationError as e:
            logger.warning(
                f"Invalid start_speaking_plan config in agent.raw_config: {e}",
                extra={"agent_id": self.agent.id},
            )
            return None
