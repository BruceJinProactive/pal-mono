from datetime import datetime, timezone

import db
from api.routes.admin._utils import get_agent_type
from api.routes.utils import map_uri_to_s3_url
from api.schemas.admin.account import Account, AccountSummary
from api.schemas.admin.agent import Agent, AgentSummary
from api.schemas.admin.checkpoint import Checkpoint
from api.schemas.admin.conversation import Conversation, ConversationDetail, Message
from api.schemas.admin.faq import FAQ
from api.schemas.admin.feedback import Feedback
from api.schemas.admin.history import ChangeField, ChangeLogDetails, ChangeLogSummary
from api.schemas.admin.integration import (
    IntegrationResponse,
    IntegrationSummaryResponse,
    ProjectIntegrationResponse,
    ProjectIntegrationSummaryResponse,
)
from api.schemas.admin.lead import Lead
from api.schemas.admin.onboarding import OnboardingProjectInfo
from api.schemas.admin.project import Project, ProjectSummary
from api.schemas.admin.prompt import Prompt, PromptDetails
from api.schemas.admin.subscription import (
    ProjectSubscription,
    StripeCustomer,
    Subscription,
    SubscriptionPlan,
)
from api.schemas.admin.voice_config import VoiceConfig
from db.repositories.prompt_repository import PromptRepository
from db.tables.accounts import OnboardingMethod
from services.admin_service.schema import CreatedProjectInfo
from services.integration_service.schema import IntegrationDetail
from services.subscription_service._stripe_customer import CustomerInfo


def _str_to_bool(value) -> bool:
    """Convert string to boolean, treating 'false' as False."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in ("true", "1", "yes")
    return bool(value) if value is not None else False


def build_account(account: db.Account) -> Account:
    return Account(
        id=str(account.id),
        name=account.name,
        display_name=account.display_name or account.name,
        icon_url=map_uri_to_s3_url(account.icon_uri),
        industry=account.industry,
        business_description=account.business_description,
        business_faq=account.business_faq,
        business_promotions=account.business_promotions,
        business_catalog=account.business_catalog,
        business_others=account.business_others,
        stripe_customer_id=account.stripe_customer_id,
        projects=[str(project.id) for project in account.projects],
        agents=[str(agent.id) for agent in account.agents],
        status=account.status,
        owner=account.owner,
        segment=account.segment.value if account.segment else None,
        tier=account.tier.value if account.tier else None,
        notes=account.notes,
        created_at=int(account.created_at.timestamp()),
        updated_at=int(account.updated_at.timestamp() if account.updated_at else 0),
        contract_signed=account.contract_signed,
        terms_accepted=account.terms_accepted,
        phone_number=account.phone_number,
        channels=account.channels,
        onboarding_method=account.onboarding_method
        or OnboardingMethod.manage_onboarding,
    )


def build_account_summary(account: db.Account) -> AccountSummary:
    """Build a simplified account summary for list responses"""
    return AccountSummary(
        id=account.id,
        name=account.name,
        display_name=account.display_name or account.name,
        icon_url=map_uri_to_s3_url(account.icon_uri),
        industry=account.industry,
        status=account.status,
        owner=account.owner,
        segment=account.segment.value if account.segment else None,
        tier=account.tier.value if account.tier else None,
        contract_signed=account.contract_signed,
        terms_accepted=account.terms_accepted,
        notes=account.notes,
        phone_number=account.phone_number,
        channels=account.channels,
        onboarding_method=account.onboarding_method,
        created_at=int(account.created_at.timestamp()),
        updated_at=int(account.updated_at.timestamp()) if account.updated_at else None,
    )


def build_agent(agent: db.Agent) -> Agent:
    return Agent(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        communication_style=agent.communication_style,
        interaction_guidelines=agent.interaction_guidelines,
        raw_config=agent.raw_config,
        created_at=int(agent.created_at.timestamp()),
        updated_at=int(agent.updated_at.timestamp() if agent.updated_at else 0),
        projects=[str(project.id) for project in agent.projects],
        account_id=agent.account_id,
        agent_type=get_agent_type(agent),
        voice_id=agent.voice_id,
        greeting_message=agent.greeting_message,
        speech_rate=agent.speech_rate,
        background_noise=agent.background_noise,
        language=agent.language,
        filler_words=agent.filler_words,
        memory_enabled=agent.memory_enabled,
    )


def build_agent_summary(agent: db.Agent) -> AgentSummary:
    return AgentSummary(
        id=agent.id,
        name=agent.name,
        agent_type=get_agent_type(agent),
        language=agent.language,
    )


def build_project(project: db.Project) -> Project:
    return Project(
        id=project.id,
        name=project.name,
        display_name=project.display_name,
        raw_config=project.raw_config,
        channel_identifiers=project.channel_identifiers or [],
        agent_id=project.agent_id,
        account_id=project.account_id,
        store_hours=project.store_hours,
        address=project.address,
        product_info=project.product_info,
        service_instruction=project.service_instruction,
        timezone=project.timezone,
        transfer_message=project.transfer_message,
        transfer_phone_number=project.transfer_phone_number,
        reservation_link=project.reservation_link,
        ordering_link=project.ordering_link,
        created_at=int(project.created_at.timestamp()),
        updated_at=int(project.updated_at.timestamp() if project.updated_at else 0),
    )


def build_project_summary(project: db.Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        display_name=project.display_name,
        channel_identifiers=project.channel_identifiers,
        address=project.address,
        timezone=project.timezone,
        created_at=int(project.created_at.timestamp()),
        updated_at=int(project.updated_at.timestamp() if project.updated_at else 0),
    )


def build_message(message: db.Message) -> Message:
    text = message.body.get("text") or {}
    extras = message.body.get("extras") or {}
    return Message(
        id=message.id,
        content=text.get("body"),
        type=message.body.get("type"),
        channel=message.body.get("channel"),
        author_type=message.body.get("author_type"),
        metadata=message.body.get("metadata"),
        channel_info=message.body.get("channel_info"),
        sender_identifier=message.body.get("sender_identifier"),
        recipient_identifier=message.body.get("recipient_identifier"),
        escalated=_str_to_bool(extras.get("escalated")),
        sent_at=message.body.get("timestamp"),
        conversation_id=message.conversation_id,
        created_at=message.created_at,
        media=message.body.get("media"),
    )


def build_feedback(
    feedback: db.Feedback, message: db.Message | None = None
) -> Feedback:
    if not message:
        # fallback to retrieving the message from the db
        message = feedback.message
    return Feedback(
        id=str(feedback.id),
        message_id=str(feedback.message_id),
        message_content=message.body.get("text", {}).get("body"),
        author_identifier=feedback.author_identifier,
        reaction=feedback.reaction,
        tags=feedback.tags,
        note=feedback.note,
        timestamp=feedback.updated_at.isoformat(),
    )


def build_conversation(
    conversation: db.Conversation,
    message_count: int,
    last_message: db.Message,
) -> Conversation:
    return Conversation(
        id=conversation.id,
        status=conversation.status.value,
        project_id=conversation.project_id,
        created_at=conversation.created_at,
        last_message=build_message(last_message) if last_message else None,
        total_messages=message_count,
    )


def build_conversation_detail(conversation: db.Conversation) -> ConversationDetail:
    """Build conversation detail response without messages"""
    return ConversationDetail(
        id=conversation.id,
        status=conversation.status.value,
        project_id=conversation.project_id,
        user_id=conversation.user_id,
        is_test=conversation.is_test,
        vapi_control_url=conversation.vapi_control_url,
        call_id=conversation.call_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def build_change_log_summary(
    change_log: db.ChangeLog,
) -> ChangeLogSummary:
    return ChangeLogSummary(
        id=change_log.id,
        account_id=change_log.account_id,
        resource_type=change_log.resource_type,
        resource_id=change_log.resource_id,
        author=change_log.author,
        action=change_log.action.value,
        created_at=change_log.created_at,
    )


def build_change_log_details(
    change_log: db.ChangeLog,
) -> ChangeLogDetails:
    fields = [
        ChangeField(
            field=f.field,
            old_value=f.old_value,
            new_value=f.new_value,
        )
        for f in change_log.fields
    ]
    return ChangeLogDetails(
        info=build_change_log_summary(change_log),
        fields=fields,
    )


def build_lead(lead: db.Lead) -> Lead:
    return Lead(
        id=lead.id,
        business_name=lead.business_name,
        business_address=lead.business_address,
        logo_uri=map_uri_to_s3_url(lead.logo_uri),
        segment=lead.segment,
        tier=lead.tier,
        owner=lead.owner,
        hubspot_record_id=lead.hubspot_record_id,
        status=lead.status,
        notes=lead.notes,
        pos=lead.pos,
        channels=lead.channels,
        contract_signed=lead.contract_signed,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def build_subscription_plan(plan: db.SubscriptionPlan) -> SubscriptionPlan:
    return SubscriptionPlan(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        tier=plan.tier,
        features_included=plan.features_included or [],
        features_excluded=plan.features_excluded or [],
        call_quota=plan.call_quota,
        order_quota=plan.order_quota,
        call_overage_charge=plan.call_overage_charge,
        order_overage_charge=plan.order_overage_charge,
        free_trial_days=plan.free_trial_days,
        credit_amount=plan.credit_amount,
        monthly_fee=plan.monthly_fee,
        active=plan.active,
        sort_id=plan.sort_id,
        hidden=bool(plan.hidden),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def build_subscription(subscription: db.AccountSubscription) -> Subscription:
    in_trial = (
        (
            subscription.trial_start_date
            <= datetime.now(timezone.utc)
            <= subscription.start_date
        )
        if subscription.trial_start_date
        else False
    )
    return Subscription(
        id=subscription.id,
        external_id=subscription.external_id,
        version=subscription.version,
        account_id=subscription.account_id,
        subscription_plan=build_subscription_plan(subscription.subscription_plan),
        payment_method=subscription.payment_method,
        status=subscription.status,
        in_trial=in_trial,
        trial_start_date=subscription.trial_start_date,
        start_date=subscription.start_date,
        end_date=subscription.end_date,
        stripe_subscription_id=subscription.stripe_subscription_id,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


def build_integration(integration: IntegrationDetail) -> IntegrationResponse:
    """Build an integration response with actual token values."""
    return IntegrationResponse(
        id=integration.id,
        account_id=integration.account_id,
        provider=integration.provider,
        integration_type=integration.integration_type,
        auth_type=integration.auth_type,
        business_id=integration.business_id,
        raw_config=integration.raw_config or {},
        access_token=integration.access_token,
        refresh_token=integration.refresh_token,
        client_id=integration.client_id,
        client_secret=integration.client_secret,
        api_key=integration.api_key,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        expires_at=integration.expires_at,
    )


def build_integration_summary(
    integration: IntegrationDetail,
) -> IntegrationSummaryResponse:
    """Build an integration summary response."""
    return IntegrationSummaryResponse(
        id=integration.id,
        provider=integration.provider,
        integration_type=integration.integration_type,
        auth_type=integration.auth_type,
        business_id=integration.business_id,
        created_at=integration.created_at,
    )


def build_project_integration(
    project_integration: db.ProjectIntegration,
) -> ProjectIntegrationResponse:
    """Build a project integration response."""
    return ProjectIntegrationResponse(
        id=project_integration.id,
        project_id=project_integration.project_id,
        integration_id=project_integration.integration_id,
        store_identifier=project_integration.store_identifier,
        tool_name=project_integration.tool_name,
        config=project_integration.config or {},
        created_at=project_integration.created_at,
    )


def build_project_integration_summary(
    project_integration: db.ProjectIntegration,
) -> ProjectIntegrationSummaryResponse:
    """Build a project integration summary response."""
    return ProjectIntegrationSummaryResponse(
        id=project_integration.id,
        integration_id=project_integration.integration_id,
        store_identifier=project_integration.store_identifier,
        tool_name=project_integration.tool_name,
        config=project_integration.config or {},
        created_at=project_integration.created_at,
    )


def build_project_subscription(
    project_subscription: db.ProjectSubscription,
    project: db.Project,
) -> ProjectSubscription:
    """Build a project subscription response with project details."""
    return ProjectSubscription(
        id=project_subscription.id,
        project=build_project_summary(project),
        subscription_id=project_subscription.subscription_id,
        deleted=project_subscription.deleted,
        created_at=project_subscription.created_at,
        updated_at=project_subscription.updated_at,
    )


def build_prompt_details(prompt_details: db.PromptDetails) -> PromptDetails:
    return PromptDetails(
        id=prompt_details.id,
        prompt_id=prompt_details.prompt_id,
        version_number=prompt_details.version_number,
        content=prompt_details.content,
        change_summary=prompt_details.change_summary,
        created_by=prompt_details.created_by,
        created_at=prompt_details.created_at,
        updated_at=prompt_details.updated_at or datetime.now(),
    )


def build_prompt(prompt: db.Prompt, session=None) -> Prompt:
    details = None
    if session:
        prompt_repository = PromptRepository(session, auto_commit=False)
        latest_details = prompt_repository.get_latest_prompt_details(prompt.id)
        if latest_details:
            details = build_prompt_details(latest_details)

    return Prompt(
        id=prompt.id,
        name=prompt.name,
        default_prompt_id=prompt.default_prompt_id,
        channel=(
            [
                channel.value if hasattr(channel, "value") else channel
                for channel in prompt.channel
            ]
            if prompt.channel
            else []
        ),
        resource_id=prompt.resource_id,
        resource_type=prompt.resource_type,
        deleted=prompt.deleted,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at or datetime.now(),
        details=details,
    )


def build_onboarding_project_info(
    project_info: CreatedProjectInfo,
) -> OnboardingProjectInfo:
    """Build OnboardingProjectInfo from CreatedProjectInfo."""
    return OnboardingProjectInfo(
        project_id=str(project_info["project_id"]),
        project_name=str(project_info["project_name"]),
        agent_id=str(project_info["agent_id"]),
        enable_web_widget=bool(project_info["enable_web_widget"]),
    )


def build_voice_config(voice_config: db.VoiceConfig) -> VoiceConfig:
    """Build VoiceConfig from database VoiceConfig."""
    return VoiceConfig(
        id=voice_config.id,
        project_id=voice_config.project_id,
        language=voice_config.language,
        voice_id=voice_config.voice_id,
        replacements=voice_config.replacements,
        first_message=voice_config.first_message,
        transfer_message=voice_config.transfer_message,
        speech_rate=voice_config.speech_rate,
        background_sound=voice_config.background_sound,
        raw_config=voice_config.raw_config,
        created_at=int(voice_config.created_at.timestamp()),
        updated_at=int(
            voice_config.updated_at.timestamp() if voice_config.updated_at else 0
        ),
    )


def build_stripe_customer(customer_info: CustomerInfo) -> StripeCustomer:
    return StripeCustomer(
        id=customer_info.id,
        name=customer_info.name,
        email=customer_info.email,
        balance=customer_info.balance or 0,
        currency=customer_info.currency or "usd",
    )


def build_checkpoint(checkpoint: db.CheckPoint) -> Checkpoint:
    """Build Checkpoint response from database CheckPoint."""
    return Checkpoint(
        id=str(checkpoint.id),
        project_id=str(checkpoint.project_id),
        name=checkpoint.name,
        description=checkpoint.description,
        image_url=checkpoint.image_url,
        is_active=checkpoint.is_active,
        group=checkpoint.group,
        rules=checkpoint.rules,
    )


def build_faq(faq: db.FAQ) -> FAQ:
    """Build FAQ response from database FAQ."""
    return FAQ(
        id=str(faq.id),
        account_id=str(faq.account_id),
        question=faq.question,
        answer=faq.answer,
        created_at=faq.created_at.isoformat(),
        updated_at=(
            faq.updated_at.isoformat() if faq.updated_at else faq.created_at.isoformat()
        ),
    )
