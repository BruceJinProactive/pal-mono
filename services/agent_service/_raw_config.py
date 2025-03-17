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
            raise ValueError("`agent_raw_config` is not provided.")

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
        persona = raw_config.get("persona", None)
        if persona is None:
            raise ValueError("`persona` is not provided in `agent_raw_config`.")

        # Use the name, role, system_prompt from the persona section
        name = persona.get("name", None)
        role = persona.get("role", None)
        system_prompt = persona.get("system_prompt", None)

        if name is None:
            raise ValueError("`persona.name` is not provided in `agent_raw_config`.")

        if role is None:
            raise ValueError("`persona.role` is not provided in `agent_raw_config`.")

        if system_prompt is None:
            raise ValueError(
                "`persona.system_prompt` is not provided in `agent_raw_config`."
            )

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
        )

    def _get_agent_knowledge(self, raw_config: dict[str, Any]) -> KnowledgeConfig:
        # Extract the knowledge section of the raw config
        knowledge = raw_config.get("knowledge", None)

        if knowledge is None:
            logger.info("`knowledge` is not provided in `agent_raw_config`.")
            return KnowledgeConfig(enabled=False)

        # Use the identifier, provider, settings from the knowledge section
        identifier = knowledge.get("identifier", None)
        if identifier is None:
            raise ValueError(
                "`knowledge.identifier` is not provided in `agent_raw_config`."
            )
        provider = knowledge.get("provider", None)

        if provider is None:
            raise ValueError(
                "`knowledge.provider` is not provided in `agent_raw_config`."
            )

        # Check if provider is supported
        provider = KnowledgeProvider(provider)
        if provider not in KnowledgeProvider:
            raise ValueError(
                "`knowledge.provider` is not valid."
                f"Supported providers: {KnowledgeProvider}"
            )
        elif provider == KnowledgeProvider.LLAMAINDEX:
            settings = knowledge.get("settings", None)
            if settings is None:
                raise ValueError(
                    "`knowledge.settings` is not provided in `agent_raw_config`."
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
        # Disable knowledge for Windsor agent
        if self.account_name == "windsor":
            return KnowledgeConfig(
                enabled=False,
                provider=provider,
                identifier=identifier,
                settings=settings,
            )
        return KnowledgeConfig(
            enabled=True,
            provider=provider,
            identifier=identifier,
            settings=settings,
        )

    def _get_agent_tools(self, raw_config: dict[str, Any]) -> ToolConfig:
        # TODO: adora_tool should be removed from the generic build and based in via raw_config
        knowledge = self._get_agent_knowledge(raw_config)

        # Get the client section of the raw config
        client = raw_config.get("client", None)
        if knowledge is None:
            raise ValueError("`client` is not provided in `agent_raw_config`.")

        store_id = client.get("store_id", None)
        if store_id is None:
            raise ValueError("`client.store_id` is not provided in `agent_raw_config`.")

        # TODO: We need to create a placeholder for agent that doesn't need a tool
        if self.account_name in ["palona", "wyze", "samsung_uk"]:
            return ToolConfig(
                identifiers=[ToolIdentifier(tool_name="calculator_tool")],
            )

        if self.account_name == "mindzero":
            # TODO: use store_id for now (instead of location_id) but we should move these
            # agent specific / client specific details to the raw_config of tools
            return ToolConfig(
                identifiers=[
                    ToolIdentifier(
                        tool_name="booking_tool", args={"location_id": store_id}
                    )
                ],
            )

        tool_map = {
            "pizzamyheart": "adora_tool",
            "palona-pizza": "adora_tool",
            "windsor": "windsor_tool",
        }

        return ToolConfig(
            identifiers=[
                ToolIdentifier(
                    tool_name=tool_map[self.account_name],
                    args={
                        "store_id": store_id,
                        "agent_id": self.agent_id,  # pass as UUID
                        "account_id": self.account_id,  # pass as UUID
                        "account_name": self.account_name,
                        "user_id": self.user_id,  # pass as UUID
                        "session_id": self.conversation_id,  # pass as UUID
                        "namespace": knowledge.settings.namespace,  # type: ignore
                    },
                )
            ],
        )
