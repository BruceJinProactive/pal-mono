from datetime import datetime
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from jinja2.sandbox import SandboxedEnvironment
from pydantic import ValidationError

import db
from agent import (
    AgentConfig,
    AgentFramework,
    AgentMetadata,
    AgentPersona,
    ClientConfig,
    KnowledgeConfig,
    KnowledgeProvider,
    LlamaIndexSettings,
    MemoryConfig,
    ModelConfig,
    ToolConfig,
    ToolIdentifier,
    ToolMetadata,
)
from agent.config import BackgroundSpeechDenoisingPlan, VoiceConfig
from agent.knowledge import KnowledgeConfigSettings
from agent.memory import MemoryProvider
from agent.model import ModelProvider
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
        client_config: ClientConfig | None = None,
        integration: IntegrationDetail | None = None,
    ):
        self.agent = agent
        self.project = project
        self.account = account
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.client_config = client_config
        self.channel = channel
        self.integration = integration

    def build(self) -> AgentConfig:
        try:
            # NOTE: For now use only client data from project raw config
            # TODO: Merge client data from agent raw config and project raw config
            client_data = {}

            # Add timezone datetime information
            if self.project.raw_config:
                client_data = self.project.raw_config.get("client_data", {})

            self.client_config = ClientConfig(data=client_data)

            memory_provider = self.agent.raw_config.get(
                "memory_provider", MemoryProvider.DEFAULT
            )

            return AgentConfig(
                persona=self._get_agent_persona(self.channel),
                model=self._get_agent_model_config(),
                memory=MemoryConfig(
                    enabled=True,
                    provider=memory_provider,
                    identifier=self.account.name,
                    instruction="Don't remember the user's gender.",
                ),
                knowledge=self._get_agent_knowledge(),
                tool=self._get_agent_tools(),
                metadata=AgentMetadata(
                    account_name=self.account.name,
                    agent_id=str(self.agent.id),
                    user_id=str(self.user_id),
                    session_id=str(self.conversation_id),
                    framework=self.agent.raw_config.get(
                        "agent_framework", AgentFramework.AGNO
                    ),
                ),
                client=self.client_config,
                additional_context=self._get_additional_context(),
                voice_config=VoiceConfig(
                    enabled=self.agent.raw_config.get(
                        "vapi_voice_config_enabled", False
                    ),
                    greeting_message=self._render_greeting_message(),
                    voice_id=self.agent.voice_id,
                    speech_rate=self.agent.speech_rate,
                    background_noise=self.agent.background_noise,
                    background_speech_denoising_plan=self._get_background_speech_denoising_plan(),
                    language=self.agent.language,
                    tool_calling_filler_words=self.agent.raw_config.get(
                        "tool_calling_filler_words", []
                    ),
                ),
            )
        except ValueError as e:
            raise ValueError(f"Invalid RawConfig: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to convert to AgentConfig: {e}") from e

    def _get_agent_persona(self, channel: Channel) -> AgentPersona:
        # Extract the persona section of the raw config
        raw_persona = self.agent.raw_config.get("persona", {})
        dynamic_prompt = self.agent.raw_config.get("dynamic_prompt_enabled", False)

        if not raw_persona:
            logger.info(
                "'persona' is not provided in 'agent.raw_config'.",
                extra={
                    "agent_id": self.agent.id,
                },
            )

        # Use the name, role, system_prompt from the persona section
        name = (self.agent.name if dynamic_prompt else raw_persona.get("name")) or ""
        role = (
            self.agent.agent_type if dynamic_prompt else raw_persona.get("role")
        ) or ""
        system_prompt = (
            self._build_agent_prompt(channel)
            if dynamic_prompt
            else raw_persona.get("system_prompt")
        )
        voice_id = raw_persona.get("voice_id") or None
        multilingual = raw_persona.get("multilingual") or False
        model_mode = raw_persona.get("model_mode") or None
        multilingual_workflow = raw_persona.get("multilingual_workflow") or False
        multilingual_squad = raw_persona.get("multilingual_squad") or False

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
            voice_id=voice_id,
            multilingual=multilingual,
            model_mode=model_mode,
            multilingual_workflow=multilingual_workflow,
            multilingual_squad=multilingual_squad,
        )

    def _get_agent_knowledge(self) -> KnowledgeConfig:
        # Extract the knowledge section of the raw config
        raw_knowledge = self.agent.raw_config.get("knowledge")

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

    def _get_agent_tools(self) -> ToolConfig:
        metadata = ToolMetadata(
            agent_id=self.agent.id,
            account_id=self.account.id,
            account_name=self.account.name,
            user_id=self.user_id,
            session_id=self.conversation_id,
            project_id=self.project.id,
            timezone=self.project.timezone,
        )

        # Extract the tools from agent config
        raw_tools = self.agent.raw_config.get("tools", {})
        raw_identifiers = raw_tools.get("identifiers", []) or []
        if not isinstance(raw_identifiers, list):
            raise ValueError("'identifiers' should be a list.")

        # Load overrides from project config
        project_tool_overrides = self._get_project_tools_override()

        seen_tools = set()
        final_identifiers: list[ToolIdentifier] = []

        for raw_tool in raw_identifiers:
            if not isinstance(raw_tool, dict):
                raise ValueError("'identifiers' should be a list of dict.")

            tool_name = raw_tool.get("tool_name", "")
            tool_args = raw_tool.get("tool_args", {})
            access_metadata = raw_tool.get("access_metadata", False)

            # Apply override if available
            if tool_name in project_tool_overrides:
                tool_override = project_tool_overrides[tool_name]
                tool_args = {
                    **tool_args,
                    **tool_override.get("tool_args", {}),
                }  # shallow merge
                access_metadata = tool_override.get("access_metadata", access_metadata)

            final_identifiers.append(
                ToolIdentifier(
                    tool_name=tool_name,
                    args=tool_args,
                    access_metadata=access_metadata,
                )
            )
            seen_tools.add(tool_name)

        # Add new tools from project config that weren't in agent config
        for tool_name, overrides in project_tool_overrides.items():
            if tool_name not in seen_tools:
                final_identifiers.append(
                    ToolIdentifier(
                        tool_name=tool_name,
                        args=overrides.get("tool_args", {}),
                        access_metadata=overrides.get("access_metadata", False),
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
