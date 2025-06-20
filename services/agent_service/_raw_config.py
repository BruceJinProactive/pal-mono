from datetime import datetime
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

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
from agent.config import StorageProvider, VoiceConfig
from agent.knowledge import KnowledgeConfigSettings
from agent.memory import MemoryProvider
from agent.model import ModelProvider
from db.tables.accounts import BusinessIndustry
from db.tables.types import AgentType, Channel, TargetTier
from services.agent_service.prompts import prompt_factory
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
    ):
        self.agent = agent
        self.project = project
        self.account = account
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.client_config = client_config
        self.channel = channel

    def build(self) -> AgentConfig:
        try:
            # NOTE: For now use only client data from project raw config
            # TODO: Merge client data from agent raw config and project raw config
            client_data = {}

            # Add timezone datetime information
            if self.project.raw_config:
                client_data = self.project.raw_config.get("client_data", {})

            self.client_config = ClientConfig(data=client_data)

            storage_provider = self.agent.raw_config.get(
                "storage_provider", StorageProvider.PALSTORAGE
            )

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
                    framework=AgentFramework.AGNO,
                ),
                client=self.client_config,
                storage_provider=storage_provider,
                additional_context=self._get_additional_context(),
                voice_config=VoiceConfig(
                    enabled=self.agent.raw_config.get(
                        "vapi_voice_config_enabled", False
                    ),
                    greeting_message=self.agent.greeting_message,
                    voice_id=self.agent.voice_id,
                    speech_rate=self.agent.speech_rate,
                    background_noise=self.agent.background_noise,
                    language=self.agent.language,
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

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
            voice_id=voice_id,
            multilingual=multilingual,
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

    def _get_agent_tools(self) -> ToolConfig:
        # Extract the knowledge section of the raw config
        raw_tools = self.agent.raw_config.get("tools")

        metadata = ToolMetadata(
            agent_id=self.agent.id,
            account_id=self.account.id,
            account_name=self.account.name,
            user_id=self.user_id,
            session_id=self.conversation_id,
        )

        if not raw_tools:
            logger.warning("'tools' is not provided in 'agent.raw_config'.")
            return ToolConfig(metadata=metadata)

        # TODO: Tool provider configuration not implemented yet (not necessary for now)

        raw_identifiers = raw_tools.get("identifiers", [])

        if not isinstance(raw_identifiers, list):
            raise ValueError("'identifiers' should be a list.")

        identifiers: list[ToolIdentifier] = []
        for raw_tool in raw_identifiers:
            if not isinstance(raw_tool, dict):
                raise ValueError("'identifiers' should be a list of dict.")

            tool_name = raw_tool.get("tool_name", "")
            tool_args = raw_tool.get("tool_args", {})
            access_metadata = raw_tool.get("access_metadata", False)

            tool = ToolIdentifier(
                tool_name=tool_name,
                args=tool_args,
                access_metadata=access_metadata,
            )
            identifiers.append(tool)

        return ToolConfig(identifiers=identifiers, metadata=metadata)

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
        info_list = prompt_factory.build(channel, self.agent.agent_type, TargetTier.t2)
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
