from datetime import datetime
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
from utils.log import logger


class RawConfig:

    def __init__(
        self,
        agent: db.Agent,
        project: db.Project,
        account: db.Account,
        user_id: UUID,
        conversation_id: UUID,
        client_config: ClientConfig | None = None,
    ):
        self.agent = agent
        self.project = project
        self.account = account
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.client_config = client_config

    def build(self) -> AgentConfig:
        try:
            # NOTE: For now use only client data from project raw config
            # TODO: Merge client data from agent raw config and project raw config
            client_data = {}

            additional_context = ""

            # Add timezone datetime information
            if self.project.raw_config:
                timezone = self.project.raw_config.get("timezone")

                if timezone:
                    # TODO: Once timezone PR is merged on Agno's side we can remove this
                    # logic and use add_datetime_to_instructions + timezone_identifier instead
                    try:
                        tz = ZoneInfo(timezone)
                        time = datetime.now(tz)

                        additional_context += f"The current time is {time}."
                    except Exception:
                        raise ValueError(f"Timezone '{timezone}' is invalid.")

                client_data = self.project.raw_config.get("client_data", {})

            self.client_config = ClientConfig(data=client_data)

            return AgentConfig(
                persona=self._get_agent_persona(),
                model=ModelConfig(
                    identifier="medium",
                ),
                memory=MemoryConfig(
                    enabled=True,
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
                additional_context=additional_context,
            )
        except ValueError as e:
            raise ValueError(f"Invalid RawConfig: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to convert to AgentConfig: {e}") from e

    def _get_agent_persona(self) -> AgentPersona:
        # Extract the persona section of the raw config
        raw_persona = self.agent.raw_config.get("persona", {})

        if not raw_persona:
            logger.info(
                "'persona' is not provided in 'agent.raw_config'.",
                extra={
                    "agent_id": self.agent.id,
                },
            )

        # Use the name, role, system_prompt from the persona section
        name = raw_persona.get("name") or self.agent.name or ""
        role = raw_persona.get("role") or self.agent.agent_type or ""
        system_prompt = raw_persona.get("system_prompt") or self._build_agent_prompt()

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
        )

    def _get_agent_knowledge(self) -> KnowledgeConfig:
        # Extract the knowledge section of the raw config
        raw_knowledge = self.agent.raw_config.get("knowledge")

        if not raw_knowledge:
            logger.warning("'knowledge' is not provided in 'agent.raw_config'.")
            return KnowledgeConfig(enabled=False)

        # Use the identifier, provider, settings from the knowledge section
        identifier = raw_knowledge.get("identifier")
        if identifier is None:
            raise ValueError(
                "'knowledge.identifier' is not provided in 'agent.raw_config'."
            )
        raw_provider = raw_knowledge.get("provider")

        if not raw_provider:
            raise ValueError(
                "'knowledge.provider' is not provided in 'agent.raw_config'."
            )

        # Check if provider is supported
        provider = KnowledgeProvider(raw_provider)
        if provider not in KnowledgeProvider:
            raise ValueError(
                "'knowledge.provider' is not valid."
                f"Supported providers: {KnowledgeProvider}"
            )
        elif provider == KnowledgeProvider.LLAMAINDEX:
            settings = raw_knowledge.get("settings")
            if settings is None:
                raise ValueError(
                    "'knowledge.settings' is not provided in 'agent.raw_config'."
                )

            # Validate that the knowledge config settings are valid for llamaindex provider
            try:
                LlamaIndexSettings.model_validate(settings)
            except ValidationError as e:
                raise ValueError(
                    "Invalid KnowledgeConfig settings for provider 'LlamaIndex'."
                ) from e
        else:
            # For other providers, settings is not required
            settings = None

        # Enable by default
        enable_knowledge = raw_knowledge.get("enabled", True)
        logger.debug(f"Knowledge enabled: {enable_knowledge}")

        return KnowledgeConfig(
            enabled=enable_knowledge,
            provider=provider,
            identifier=identifier,
            settings=settings,
        )

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
                client_config=self.client_config,
            )
            identifiers.append(tool)

        return ToolConfig(identifiers=identifiers, metadata=metadata)

    def _build_agent_prompt(self) -> str:
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

        brand_info_list = [
            ("## Description", self.account.business_description),
            ("## F.A.Q.", self.account.business_faq),
            ("## Catalog", self.account.business_catalog),
            ("## Current Promotions", self.account.business_promotions),
            ("## Others", self.account.business_others),
        ]
        agent_info_list = [
            ("## Description", self.agent.description),
            ("## Communication Style", self.agent.communication_style),
            ("## Interaction Guidelines", self.agent.interaction_guidelines),
        ]

        sections = []
        sections.extend(build_section("# Brand Information", brand_info_list))
        sections.extend(build_section("# Agent Information", agent_info_list))
        return "\n".join(sections)
