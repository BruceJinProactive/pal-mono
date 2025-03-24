from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from agent import (
    AgentConfig,
    AgentFramework,
    AgentMetadata,
    AgentPersona,
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


class RawConfig(BaseModel):
    # Agent
    agent_id: UUID
    agent_raw_config: dict[str, Any] | None

    # Project level config (e.g. pizzamyheart-default, pizzamyheart-palo-alto)
    project_raw_config: dict[str, Any] | None  # TODO: this is not used yet

    # Account
    account_id: UUID
    account_name: str

    # Session info
    user_id: UUID
    conversation_id: UUID  # Session ID

    # Agent stream
    stream: bool = False

    def build(self) -> AgentConfig:
        if self.agent_raw_config is None:
            raise ValueError("'agent_raw_config' is not provided.")

        try:
            return AgentConfig(
                persona=self._get_agent_persona(self.agent_raw_config),
                model=ModelConfig(
                    identifier="medium",
                    stream=self.stream,
                ),
                memory=MemoryConfig(
                    enabled=True,
                    identifier=self.account_name,
                    instruction="Don't remember the user's gender.",
                ),
                knowledge=self._get_agent_knowledge(self.agent_raw_config),
                tool=self._get_agent_tools(self.agent_raw_config),
                metadata=AgentMetadata(
                    account_name=self.account_name,
                    agent_id=str(self.agent_id),
                    user_id=str(self.user_id),
                    session_id=str(self.conversation_id),
                    framework=AgentFramework.AGNO,
                ),
            )
        except ValueError as e:
            raise ValueError(f"Invalid RawConfig: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to convert to AgentConfig: {e}") from e

    def _get_agent_persona(self, raw_config: dict[str, Any]) -> AgentPersona:
        # Extract the persona section of the raw config
        raw_persona = raw_config.get("persona")
        if not raw_persona:
            raise ValueError("'persona' is not provided in 'agent_raw_config'.")

        # Use the name, role, system_prompt from the persona section
        name = raw_persona.get("name")
        role = raw_persona.get("role")
        system_prompt = raw_persona.get("system_prompt")

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
        )

    def _get_agent_knowledge(self, raw_config: dict[str, Any]) -> KnowledgeConfig:
        # Extract the knowledge section of the raw config
        raw_knowledge = raw_config.get("knowledge")

        if not raw_knowledge:
            logger.info("'knowledge' is not provided in 'agent_raw_config'.")
            return KnowledgeConfig(enabled=False)

        # Use the identifier, provider, settings from the knowledge section
        identifier = raw_knowledge.get("identifier")
        if identifier is None:
            raise ValueError(
                "'knowledge.identifier' is not provided in 'agent_raw_config'."
            )
        raw_provider = raw_knowledge.get("provider")

        if not raw_provider:
            raise ValueError(
                "'knowledge.provider' is not provided in 'agent_raw_config'."
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
                    "'knowledge.settings' is not provided in 'agent_raw_config'."
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
        logger.info(f"Knowledge enabled: {enable_knowledge}")

        return KnowledgeConfig(
            enabled=enable_knowledge,
            provider=provider,
            identifier=identifier,
            settings=settings,
        )

    def _get_agent_tools(self, raw_config: dict[str, Any]) -> ToolConfig:
        # Extract the knowledge section of the raw config
        raw_tools = raw_config.get("tools")

        if not raw_tools:
            logger.info("'tools' is not provided in 'agent_raw_config'.")
            return ToolConfig()

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

            metadata: ToolMetadata | None = None
            if access_metadata:
                metadata = ToolMetadata(
                    agent_id=self.agent_id,
                    account_id=self.account_id,
                    account_name=self.account_name,
                    user_id=self.user_id,
                    session_id=self.conversation_id,
                )

            tool = ToolIdentifier(
                tool_name=tool_name,
                args=tool_args,
                access_metadata=access_metadata,
                metadata=metadata,
            )
            identifiers.append(tool)

        return ToolConfig(identifiers=identifiers)
