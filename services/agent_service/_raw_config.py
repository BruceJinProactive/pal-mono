import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from livekit import api as livekit_api
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as DBTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

import db
from agent import (
    AgentConfig,
    AgentMetadata,
    AgentPersona,
    FeatureConfig,
    KnowledgeConfig,
    KnowledgeProvider,
    LlamaIndexSettings,
    ModelConfig,
    ToolConfig,
    ToolIdentifier,
    ToolMetadata,
)
from agent.model import ModelProvider
from db.repositories.contact_repository import ContactRepositoryAsync
from db.repositories.project_contact_repository import ProjectContactRepositoryAsync
from db.tables.accounts import BusinessIndustry
from db.tables.types import AgentType, Channel, IdentifierType, TargetTier
from services import features_service
from services.agent_service._pal_agent_tool_registry import PAL_AGENT_TOOL_REGISTRY
from services.integration_service.schema import IntegrationDetail
from services.prompt_service.prompts import prompt_factory
from services.prompt_service.prompts_v2 import prompt_factory_v2
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
        receiver_identifier: str | None = None,
        project_integrations: Sequence[db.ProjectIntegration] | None = None,
        faqs: Sequence[db.FAQ] | None = None,
        room_name: str | None = None,
        participant_identity: str | None = None,
    ):
        self.agent = agent
        self.project = project
        self.account = account
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.channel = channel
        self.integration = integration
        self.sender_identifier = sender_identifier
        self.receiver_identifier = receiver_identifier
        self.project_integrations = list(project_integrations or [])
        self.faqs = list(faqs or [])
        self.room_name = room_name
        self.participant_identity = participant_identity

    async def build(self, session: Optional[AsyncSession] = None) -> AgentConfig:
        try:
            filler_words_config = self.agent.filler_words or {}

            return AgentConfig(
                persona=await self._get_agent_persona(self.channel, session),
                model=self._get_agent_model_config(),
                knowledge=self._get_agent_knowledge(),
                tool=await self._get_agent_tools(session),
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
                    language=self.agent.language.value if self.agent.language else None,
                ),
                additional_context=self._get_additional_context(),
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

    async def _get_agent_persona(
        self, channel: Channel, session: Optional[AsyncSession] = None
    ) -> AgentPersona:
        # Always use dynamic prompt behavior
        name = self.agent.name or ""
        role = self.agent.agent_type or ""
        system_prompt = await self._build_agent_prompt(channel, session)

        return AgentPersona(
            name=name,
            role=role,
            description=system_prompt,
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

            # Skip tools managed by the pal-agents tool registry
            if tool_name in PAL_AGENT_TOOL_REGISTRY:
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

            # Auto-inject store_id from store_identifier column if present
            if integration.store_identifier:
                config_copy["store_id"] = integration.store_identifier

            tools.append((tool_name, config_copy, access_metadata))

        return tools

    async def _populate_transfer_tool_args(
        self, tool_args: dict, session: Optional[AsyncSession] = None
    ) -> dict:
        """
        Populate transfer tool arguments with transfer settings.

        Builds 'transfer_destinations' dict from contacts table.
        Falls back to project.transfer_phone_number if no contacts exist (deprecated).

        Args:
            tool_args: Existing tool arguments dictionary
            session: Database session for querying contacts

        Returns:
            Updated tool arguments with transfer_destinations
        """
        updated_args = tool_args.copy()

        updated_args.pop("transfer_destinations", None)

        # Primary: Build transfer_destinations from contacts table
        if session:
            try:
                project_contact_repo = ProjectContactRepositoryAsync(session)
                contact_ids = await project_contact_repo.list_contacts_by_project(
                    self.project.id
                )

                if contact_ids:
                    contact_repo = ContactRepositoryAsync(session)
                    contacts = await contact_repo.batch_list_contacts(contact_ids)
                    # Frontend enforces one contact per role; defensive check for duplicates
                    transfer_destinations = {}
                    for contact in contacts:
                        if not contact.role or not contact.phone_number:
                            logger.warning(
                                f"Skipping contact with missing role/phone_number for project {self.project.id}"
                            )
                            continue
                        if contact.role in transfer_destinations:
                            logger.warning(
                                f"Duplicate contact role '{contact.role}' for project "
                                f"{self.project.id}, using first contact"
                            )
                        else:
                            transfer_destinations[contact.role] = contact.phone_number
                    if transfer_destinations:
                        updated_args["transfer_destinations"] = transfer_destinations
            except DBTimeoutError as e:
                # Pool exhaustion/timeout errors must propagate for proper cleanup
                logger.error(
                    f"Connection pool timeout fetching contacts for project {self.project.id}: {e}"
                )
                raise
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to fetch contacts for project {self.project.id}: {e}"
                )
                raise

            except Exception:
                logger.exception(
                    f"Unexpected error while fetching contacts for project {self.project.id}"
                )
                raise

        # transfer_message still comes from project
        if self.project.transfer_message:
            updated_args["transfer_message"] = self.project.transfer_message

        if "transfer_destinations" not in updated_args:
            # Secondary: Fallback to deprecated project.transfer_phone_number
            updated_args["transfer_destinations"] = {}

        return updated_args

    async def _get_agent_tools(
        self, session: Optional[AsyncSession] = None
    ) -> ToolConfig:
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

        # Extract store phone from receiver_identifier based on channel type
        store_phone = None
        if self.receiver_identifier:
            is_phone_channel = self.channel and self.channel.value.lower() in [
                "sms",
                "voice",
                "whatsapp",
            ]
            if is_phone_channel:
                store_phone = self.receiver_identifier

        metadata = ToolMetadata(
            agent_id=self.agent.id,
            account_id=self.account.id,
            account_name=self.account.name,
            user_id=self.user_id,
            session_id=self.conversation_id,
            project_id=self.project.id,
            timezone=self.project.timezone,
            customer_phone=customer_phone,
            store_phone=store_phone,
            channel=self.channel.value if self.channel else None,
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

        # Apply ProjectIntegration-provided tools (can be overridden by project.raw_config)
        for tool_name, tool_args, access_metadata in integration_tool_entries:
            _set_tool(tool_name, tool_args, access_metadata)

        # Apply project.raw_config tool overrides
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

        # Auto-inject livekit_tool for voice channels if not already present
        # and the project has transfer contacts configured.
        LIVEKIT_TOOL_NAMES = {"livekit_transfer_tool", "livekit_tool"}
        has_livekit_tool = bool(LIVEKIT_TOOL_NAMES & set(merged_tools.keys()))
        if self.channel == Channel.VOICE and not has_livekit_tool and session:
            has_transfer_destination = False
            try:
                project_contact_repo = ProjectContactRepositoryAsync(session)
                contact_ids = await project_contact_repo.list_contacts_by_project(
                    self.project.id
                )
                if contact_ids:
                    has_transfer_destination = True
            except (DBTimeoutError, SQLAlchemyError):
                logger.exception(
                    "[_get_agent_tools] Failed to check contacts for auto-inject "
                    "(project %s)",
                    self.project.id,
                )

            if has_transfer_destination:
                _set_tool("livekit_tool", {}, True)
                logger.debug(
                    "[_get_agent_tools] Auto-injected livekit_tool for voice channel "
                    "(project %s)",
                    self.project.id,
                )

        final_identifiers: List[ToolIdentifier] = []

        for tool_name in tool_order:
            entry = merged_tools[tool_name]
            tool_args: Dict[str, Any] = dict(entry["args"])

            if tool_name in ["livekit_transfer_tool", "livekit_tool"]:
                explicit_destinations = tool_args.get("transfer_destinations")
                explicit_destination_number = tool_args.get("destination_number")
                tool_args = await self._populate_transfer_tool_args(tool_args, session)
                if explicit_destinations:
                    # Merge: explicit destinations (e.g. SIP URIs from raw_config)
                    # override contact-derived phone numbers for the same role.
                    tool_args["transfer_destinations"] = {
                        **tool_args.get("transfer_destinations", {}),
                        **explicit_destinations,
                    }
                if explicit_destination_number and not (
                    explicit_destinations and "general" in explicit_destinations
                ):
                    # Preserve raw_config destination_number shorthand.
                    # _populate_transfer_tool_args() rebuilds transfer_destinations from
                    # contacts and would otherwise override destination_number with a
                    # potentially formatted number.
                    # Skip when explicit transfer_destinations already defines "general".
                    tool_args["transfer_destinations"] = {
                        **tool_args.get("transfer_destinations", {}),
                        "general": explicit_destination_number,
                    }
                # Inject LiveKit runtime context for SIP REFER
                logger.debug(
                    "[_get_agent_tools] LiveKit transfer tool context: "
                    "room_name=%s, participant_identity=%s",
                    self.room_name,
                    self.participant_identity,
                )
                if self.room_name and self.participant_identity:
                    tool_args["room_name"] = self.room_name
                    tool_args["participant_identity"] = self.participant_identity
                    lk_url = os.environ.get("LIVEKIT_URL", "")
                    lk_key = os.environ.get("LIVEKIT_API_KEY", "")
                    lk_secret = os.environ.get("LIVEKIT_API_SECRET", "")
                    if lk_url and lk_key and lk_secret:
                        tool_args["lk_api"] = livekit_api.LiveKitAPI(
                            url=lk_url, api_key=lk_key, api_secret=lk_secret
                        )
                    else:
                        logger.warning(
                            "[_get_agent_tools] LiveKit env vars missing — "
                            "lk_api will not be injected. "
                            "LIVEKIT_URL=%s, LIVEKIT_API_KEY=%s, LIVEKIT_API_SECRET=%s",
                            "set" if lk_url else "MISSING",
                            "set" if lk_key else "MISSING",
                            "set" if lk_secret else "MISSING",
                        )
                elif self.channel == Channel.VOICE:
                    logger.warning(
                        "[_get_agent_tools] LiveKit room context missing — "
                        "skipping lk_api injection. "
                        "room_name=%s, participant_identity=%s",
                        self.room_name,
                        self.participant_identity,
                    )

                # Populate show_agent_caller_id from project DB column
                tool_args["show_agent_caller_id"] = self.project.show_agent_caller_id

            final_identifiers.append(
                ToolIdentifier(
                    tool_name=tool_name,
                    args=tool_args,
                    access_metadata=bool(entry["access_metadata"]),
                )
            )

        # Filter out voice-only tools for non-voice channels
        VOICE_ONLY_TOOLS = {"livekit_transfer_tool", "livekit_tool"}
        if self.channel != Channel.VOICE:
            final_identifiers = [
                t for t in final_identifiers if t.tool_name not in VOICE_ONLY_TOOLS
            ]

        logger.debug(
            "[_get_agent_tools] Resolved %d tool(s) for agent %s: %s",
            len(final_identifiers),
            self.agent.id,
            [t.tool_name for t in final_identifiers],
        )

        return ToolConfig(identifiers=final_identifiers, metadata=metadata)

    def _get_agent_model_config(self) -> ModelConfig:
        raw_model = self.agent.raw_config.get("model", {})
        provider = raw_model.get("provider") or ModelProvider.OPENAI
        identifier = raw_model.get("identifier") or "gpt-4o"

        return ModelConfig(provider=provider, identifier=identifier)

    async def _build_agent_prompt(
        self, channel: Channel, session: Optional[AsyncSession] = None
    ) -> str:
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
        store_info_list = self._get_store_info()

        # Check if prompt_v2 feature is enabled for this agent
        use_v2 = False

        if session:
            try:
                use_v2 = await features_service.check_feature_enabled(
                    session=session,
                    feature="prompts_v2",
                    identifier_type=IdentifierType.agent,
                    identifier=str(self.agent.id),
                )
            except Exception as e:
                logger.warning(
                    f"[prompt_v2] Failed to check prompt_v2 feature for agent {self.agent.id}: {e}"
                )
                # Default to v1 if feature check fails
                use_v2 = False

        logger.info(
            f"[prompt_v2] Final decision for agent {self.agent.id}: use_v2={use_v2}, channel={channel}"
        )
        if use_v2:
            agent_info_list = await self._get_agent_info_v2(channel, session)
        else:
            agent_info_list = self._get_agent_info(channel)

        sections = [self._build_agent_introduction()]
        sections.extend(build_section("# Brand Information", brand_info_list))
        sections.extend(build_section("# Store Information", store_info_list))
        sections.extend(build_section("# Agent Information", agent_info_list))
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
        faq_content = None
        if self.faqs:
            faq_items = []
            for faq in self.faqs:
                faq_items.append(f"Q: {faq.question}\nA: {faq.answer}")
            faq_content = "\n\n".join(faq_items)
        else:
            faq_content = self.account.business_faq

        return [
            ("## Description", self.account.business_description),
            ("## F.A.Q.", faq_content),
            ("## Catalog", self.account.business_catalog),
            ("## Current Promotions", self.account.business_promotions),
            ("## Others", self.account.business_others),
        ]

    def _get_agent_info(self, channel: Channel):
        # default to premium tier for now.
        info_list = prompt_factory.build(
            channel,
            self.agent.agent_type,
            TargetTier.t3,
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

    async def _get_agent_info_v2(
        self, channel: Channel, session: Optional[AsyncSession] = None
    ):
        info_list = await prompt_factory_v2.build(
            channel=channel, agent_id=self.agent.id, session=session
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
