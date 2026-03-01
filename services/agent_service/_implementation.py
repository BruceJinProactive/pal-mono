import copy
import uuid
from dataclasses import asdict
from typing import Any, Dict, Literal, Optional, cast

from pal_agents import Spec
from pal_agents.spec import (
    AdoraSpec,
    FillerWordsSpec,
    GenericAPISpec,
    KnowledgeSpec,
    MemorySpec,
    ModelSpec,
    PromptSpec,
    ToolSpec,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import AgentConfig, KnowledgeConfig, LlamaIndexSettings, ToolConfig
from db.tables.change_log import ChangeResourceType
from db.tables.types import Channel, IntegrationType
from services import account_service, integration_service
from services.auth_types import UserContext
from services.history_service import change_log_context
from utils.log import logger

from . import _raw_config
from .schema import AgentParams


def _build_knowledge_spec(knowledge_config: KnowledgeConfig) -> KnowledgeSpec:
    """Convert pal-mono KnowledgeConfig to pal-agents KnowledgeSpec.

    Args:
        knowledge_config: The pal-mono knowledge configuration.

    Returns:
        KnowledgeSpec: pal-agents knowledge specification.
    """
    if not knowledge_config.enabled:
        return KnowledgeSpec(enabled=False)

    # Extract index_name and namespace from LlamaIndexSettings
    settings = knowledge_config.settings
    if settings is None:
        logger.warning("Knowledge enabled but settings is None, disabling knowledge")
        return KnowledgeSpec(enabled=False)

    if not isinstance(settings, LlamaIndexSettings):
        logger.warning(
            f"Knowledge settings is not LlamaIndexSettings (got {type(settings)}), "
            "disabling knowledge"
        )
        return KnowledgeSpec(enabled=False)

    return KnowledgeSpec(
        enabled=True,
        identifier=knowledge_config.identifier,
        index_name=settings.index_name,
        namespace=settings.namespace,
    )


def _build_tool_specs(tool_config: ToolConfig) -> list[ToolSpec]:
    """Convert pal-mono ToolConfig to pal-agents ToolSpecs.

    MVP Implementation:
    - Only includes auto-registered pal-tools (Calculator, Weather, reverse_string)
    - Skips pal-mono specific tools (toast, adora, square, etc.) that aren't
      in pal-tools registry yet
    - Excludes Yelp tools (require per-restaurant config)

    Args:
        tool_config: The pal-mono tool configuration.

    Returns:
        list[ToolSpec]: List of pal-agents tool specifications.
    """
    # Auto-registered tools in pal-tools that we can use for MVP
    PAL_TOOLS_AVAILABLE = {
        "CalculatorTool",
        "WeatherTool",
        "reverse_string",
        "vapi_tool",
        "livekit_tool",
    }

    tool_specs = []
    skipped = []
    for identifier in tool_config.identifiers:
        tool_name = identifier.tool_name

        if tool_name in PAL_TOOLS_AVAILABLE:
            tool_specs.append(
                ToolSpec(
                    tool_name=tool_name,
                    config=identifier.args,
                )
            )
        else:
            skipped.append(tool_name)

    logger.debug(
        "[_build_tool_specs] Built %d pal-agents tool spec(s): %s | skipped %d: %s",
        len(tool_specs),
        [ts.tool_name for ts in tool_specs],
        len(skipped),
        skipped,
    )

    return tool_specs


# Valid model sizes for pal-agents
ModelSize = Literal["xs", "s", "m", "l", "xl"]
DEFAULT_MODEL_SIZE: ModelSize = "m"
VALID_MODEL_SIZES: set[ModelSize] = {"xs", "s", "m", "l", "xl"}


def _normalize_model_size(model_size: Any) -> ModelSize | None:
    """Normalize and validate model size input."""
    if not isinstance(model_size, str):
        return None

    normalized = model_size.strip().lower()
    if normalized in VALID_MODEL_SIZES:
        return cast(ModelSize, normalized)
    return None


def _parse_model_spec_from_raw_config(raw_config: dict | None) -> ModelSpec:
    """Parse model size and priority from project raw_config.

    Supported formats:
    - {"model": "m"}
    - {"model": {"size": "m", "priority": true}}

    Falls back silently to defaults for missing/invalid values.
    """
    model_spec = ModelSpec(size=DEFAULT_MODEL_SIZE)
    if not isinstance(raw_config, dict):
        return model_spec

    raw_model = raw_config.get("model")

    if isinstance(raw_model, str):
        parsed_size = _normalize_model_size(raw_model)
        if parsed_size is not None:
            model_spec.size = parsed_size
        return model_spec

    if isinstance(raw_model, dict):
        parsed_size = _normalize_model_size(raw_model.get("size"))
        if parsed_size is not None:
            model_spec.size = parsed_size

        priority_value = raw_model.get("priority")
        if isinstance(priority_value, bool):
            model_spec.priority = priority_value

    return model_spec


def _build_generic_api_spec_from_raw_config(raw_config: dict) -> GenericAPISpec:
    """Build GenericAPISpec from project raw_config.

    Extracts generic_api configuration from the project's raw_config and
    constructs a GenericAPISpec for the pal-agents framework. API documentation
    is intentionally not included here - it should be injected via the prompt system.

    Auth configuration format:
        {"auth": {"type": "bearer", "token": "..."}}
        {"auth": {"type": "basic", "username": "...", "password": "..."}}

    Args:
        raw_config: The project's raw_config dictionary.

    Returns:
        GenericAPISpec: Configuration for the generic API provider.
            Returns disabled spec if generic_api is not enabled.
    """
    generic_api_config = raw_config.get("generic_api", {})

    if not generic_api_config.get("enabled"):
        return GenericAPISpec()

    return GenericAPISpec(
        enabled=True,
        api_docs="",  # Docs come from prompt system, not here
        base_url=generic_api_config.get("base_url"),
        auth=generic_api_config.get("auth"),
        allowed_paths=generic_api_config.get("allowed_paths", []),
        timeout=generic_api_config.get("timeout", 10.0),
        inject=generic_api_config.get("inject"),
    )


def _build_adora_spec_from_raw_config(raw_config: dict) -> AdoraSpec:
    """Build AdoraSpec from project raw_config.

    Extracts adora configuration from the project's raw_config and constructs
    an AdoraSpec for the pal-agents framework.

    Args:
        raw_config: The project's raw_config dictionary.

    Returns:
        AdoraSpec: Configuration for the adora provider.
            Returns disabled spec if adora is not enabled.
    """
    adora_config = raw_config.get("adora", {})

    if not adora_config.get("enabled"):
        return AdoraSpec()

    adora_spec_kwargs: dict[str, Any] = {"enabled": True}
    for field in [
        "menu_data",
        "coupon_data",
        "base_url",
        "auth",
        "allowed_paths",
        "timeout",
        "inject",
        "store_id",
        "customer_email",
        "tool_name",
        "debug",
    ]:
        if field in adora_config:
            adora_spec_kwargs[field] = adora_config[field]

    return AdoraSpec(**adora_spec_kwargs)


def _agent_config_to_spec(
    agent_config: AgentConfig,
    model_spec: ModelSpec | None = None,
    generic_api_spec: GenericAPISpec | None = None,
    adora_spec: AdoraSpec | None = None,
) -> Spec:
    """Convert pal-mono AgentConfig to pal-agents Spec.

    This is a pure conversion function with no side effects or database access.
    All data loading is handled by construct_agent_config().

    Args:
        agent_config: The fully-built pal-mono agent configuration.
        model_spec: Model settings from project raw_config
            (defaults to ModelSpec(size=DEFAULT_MODEL_SIZE)).
        generic_api_spec: Optional GenericAPISpec for external API calling.
        adora_spec: Optional AdoraSpec for deterministic adora ordering.

    Returns:
        Spec: pal-agents specification ready for Agent instantiation.
    """
    # ========== Build PromptSpec ==========
    # persona.description contains the full system prompt from _build_agent_prompt()
    prompt_spec = PromptSpec(
        instructions=agent_config.persona.description or "",
        name=agent_config.persona.name,
        role=agent_config.persona.role,
    )

    # ========== Build KnowledgeSpec ==========
    knowledge_spec = _build_knowledge_spec(agent_config.knowledge)

    # ========== Build MemorySpec ==========
    memory_spec = MemorySpec(
        enabled=agent_config.memory.enabled,
        scope_to_account=True,  # Always scope for multi-tenant isolation
    )

    # ========== Build ToolSpecs ==========
    tool_specs = _build_tool_specs(agent_config.tool)

    # ========== Build ModelSpec ==========
    effective_model_spec = model_spec or ModelSpec(size=DEFAULT_MODEL_SIZE)

    # ========== Build FillerWordsSpec ==========
    filler_words_spec = FillerWordsSpec(
        agent_id=agent_config.metadata.agent_id,
        account_name=agent_config.metadata.account_name,
        chat_filler_words_percentage=agent_config.feature_config.chat_filler_words_percentage,
        tool_calling_filler_words_percentage=agent_config.feature_config.tool_calling_filler_words_percentage,
    )

    # ========== Build final Spec ==========
    return Spec(
        prompt=prompt_spec,
        knowledge=knowledge_spec,
        memory=memory_spec,
        tools=tool_specs,
        model=effective_model_spec,
        generic_api=generic_api_spec or GenericAPISpec(),
        adora=adora_spec or AdoraSpec(),
        filler_words=filler_words_spec,
    )


async def construct_agent_spec(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel: Channel,
    sender_identifier: str | None = None,
    receiver_identifier: str | None = None,
    raw_config: dict | None = None,
    room_name: str | None = None,
    participant_identity: str | None = None,
) -> Spec:
    """Build a pal_agents.Spec from database configuration.

    This function reuses construct_agent_config() to load all database data
    and build the AgentConfig, then converts it to a pal-agents Spec.

    Args:
        session: Async database session.
        agent_id: The agent ID.
        user_id: The user ID.
        project_id: The project ID.
        conversation_id: The conversation (session) ID.
        channel: Communication channel (sms, voice, web).
        sender_identifier: Phone number or user identifier.
        receiver_identifier: Receiver identifier for phone channels (optional).
        raw_config: Project raw_config dict (if provided, skips extra DB fetch).

    Returns:
        Spec: pal-agents specification with prompt, knowledge, memory, and tools.

    Raises:
        ValueError: If agent_id or project_id is invalid (from construct_agent_config).
    """
    # Reuse existing construct_agent_config - it handles all database operations:
    # - Loads agent, project from database
    # - Gets POS integration
    # - Loads FAQs
    # - Builds RawConfig with full prompt logic
    # - Returns complete AgentConfig
    agent_config = await construct_agent_config(
        db_session=session,
        agent_id=agent_id,
        user_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
        channel=channel,
        sender_identifier=sender_identifier,
        receiver_identifier=receiver_identifier,
        room_name=room_name,
        participant_identity=participant_identity,
    )

    # Use provided raw_config or default to empty dict
    effective_raw_config = raw_config or {}

    generic_api_spec = _build_generic_api_spec_from_raw_config(effective_raw_config)
    adora_spec = _build_adora_spec_from_raw_config(effective_raw_config)
    model_spec = _parse_model_spec_from_raw_config(effective_raw_config)

    # Convert AgentConfig to pal-agents Spec (pure conversion, no DB access)
    return _agent_config_to_spec(
        agent_config,
        model_spec=model_spec,
        generic_api_spec=generic_api_spec,
        adora_spec=adora_spec,
    )


async def construct_agent_config(
    db_session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel: Channel,
    sender_identifier: str | None = None,
    receiver_identifier: str | None = None,
    room_name: str | None = None,
    participant_identity: str | None = None,
) -> AgentConfig:
    """
    Builds an Agent Config based on the Raw Config.

    Args:
        db_session (AsyncSession): The database session.
        agent_id (uuid.UUID): The agent id.
        user_id (uuid.UUID): The user id.
        project_id (uuid.UUID): The project id.
        conversation_id (uuid.UUID): The conversation (session) id of the user-agent interaction.
        channel (Channel): For which comm channel should this agent config build for, e.g. sms, voice
        sender_identifier (str | None): The sender identifier (phone for voice/sms, user ID for other channels) (optional).
        receiver_identifier (str | None): The receiver identifier (store phone for voice/sms) (optional).

    Raises:
        ValueError: If the agent_id or project_id is invalid.

    Returns:
        AgentConfig: The agent configuration object.
    """

    # Retrieve the agent from the database
    agent_repository = db.AgentRepositoryAsync(db_session)
    db_agent = await agent_repository.get_agent(agent_id=agent_id)
    if db_agent is None:
        raise ValueError("Invalid agent_id")

    # Retrieve the project from the database
    project_repository = db.ProjectRepositoryAsync(db_session)
    db_project = await project_repository.get_project(project_id)
    if db_project is None:
        raise ValueError("Invalid project_id")

    integration = await integration_service.async_get_integration_by_project_and_type(
        db_session, db_project.account_id, db_project.id, IntegrationType.pos
    )

    result = await db_session.execute(
        select(db.ProjectIntegration).filter(
            db.ProjectIntegration.project_id == db_project.id
        )
    )
    project_integrations = list(result.scalars())

    # Fetch FAQs for the account and project (combined)
    faq_result = await db_session.execute(
        select(db.FAQ)
        .filter(db.FAQ.account_id == db_agent.account.id)
        .filter((db.FAQ.project_id.is_(None)) | (db.FAQ.project_id == project_id))
        .order_by(db.FAQ.project_id.is_(None).desc())
    )
    faqs = list(faq_result.scalars())

    raw_config = _raw_config.RawConfig(
        agent=db_agent,
        project=db_project,
        account=db_agent.account,
        user_id=user_id,
        conversation_id=conversation_id,
        channel=channel,
        integration=integration,
        sender_identifier=sender_identifier,
        receiver_identifier=receiver_identifier,
        project_integrations=project_integrations,
        faqs=faqs,
        room_name=room_name,
        participant_identity=participant_identity,
    )

    # Convert blueprint to agent config
    return await raw_config.build(session=db_session)


async def get_agent_async(
    async_session: AsyncSession, agent_id: uuid.UUID
) -> Optional[db.Agent]:
    """Retrieve an agent by ID asynchronously."""
    agent_repository = db.AgentRepositoryAsync(async_session)
    agent = await agent_repository.get_agent(agent_id=agent_id)
    return agent


def get_agent(session: Session, agent_id: uuid.UUID) -> Optional[db.Agent]:
    # Retrieve the agent from the database
    agent_repository = db.AgentRepository(session)
    agent = agent_repository.get_agent(agent_id=agent_id)
    return agent


def replace_agent_config(
    session: Session, agent_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    agent_repository = db.AgentRepository(session)
    agent_repository.replace_agent_config(agent_id=agent_id, config=config)


def create_agent(
    session: Session,
    context: UserContext,
    account_name: str,
    params: AgentParams,
    auto_commit: bool,
) -> db.Agent:
    # Create an agent for the given account
    account = account_service.get_account(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} does not exist")
    agent_repository = db.AgentRepository(session, auto_commit=False)

    agent_params = asdict(params)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Agent,
        author=context.email,
        account_id=account.id,
        auto_commit=auto_commit,
    ) as ctx:
        agent = agent_repository.create_agent(account.id, **agent_params)
        ctx.resource_id = str(agent.id)
        ctx.new_record = agent

    return agent


def update_agent(
    session: Session,
    context: UserContext,
    agent_id: uuid.UUID,
    params: AgentParams,
    expected_version: int | None = None,
) -> db.Agent:
    # Update the specified agent with the provided params
    agent_repository = db.AgentRepository(session)

    existing_agent = agent_repository.get_agent(agent_id)
    if not existing_agent:
        raise ValueError(f"Agent with id {agent_id} not found")

    old_agent = copy.copy(existing_agent)

    agent_params = asdict(params)

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Agent,
        author=context.email,
        account_id=existing_agent.account.id,
        resource_id=str(agent_id),
        old_record=old_agent,
    ) as ctx:
        new_agent = agent_repository.update_agent(
            agent_id, expected_version, **agent_params
        )
        if new_agent is None:
            raise ValueError(f"Failed to update agent {agent_id}")
        ctx.new_record = new_agent
        return new_agent


def delete_agent(session: Session, context: UserContext, agent_id: uuid.UUID):
    agent_repository = db.AgentRepository(session, auto_commit=False)

    existing_agent = agent_repository.get_agent(agent_id)
    if not existing_agent:
        return

    with change_log_context(
        session=session,
        resource_type=ChangeResourceType.Agent,
        author=context.email,
        account_id=existing_agent.account.id,
        resource_id=str(existing_agent.id),
        old_record=existing_agent,
    ):
        agent_repository.delete_agent(agent_id)
