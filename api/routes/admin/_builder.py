import db
from api.routes.admin._utils import get_agent_type
from api.routes.utils import map_uri_to_s3_url
from api.schemas.admin.account import Account, AccountSummary
from api.schemas.admin.agent import Agent, AgentSummary
from api.schemas.admin.conversation import Message, UserSession
from api.schemas.admin.feedback import Feedback
from api.schemas.admin.history import ChangeField, ChangeLogDetails, ChangeLogSummary
from api.schemas.admin.lead import Lead
from api.schemas.admin.project import Project, ProjectSummary


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
        projects=[str(project.id) for project in account.projects],
        agents=[str(agent.id) for agent in account.agents],
        status=account.status,
        lead_id=account.lead_id,
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
    )


def build_agent_summary(agent: db.Agent) -> AgentSummary:
    return AgentSummary(
        id=agent.id,
        name=agent.name,
        agent_type=get_agent_type(agent),
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
        created_at=int(project.created_at.timestamp()),
        updated_at=int(project.updated_at.timestamp() if project.updated_at else 0),
    )


def build_project_summary(project: db.Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        display_name=project.display_name,
        channel_identifiers=project.channel_identifiers,
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
        escalated=bool(extras.get("escalated")),
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


def build_user_session(
    user_session: db.Conversation,
    message_count: int,
    last_message: db.Message,
) -> UserSession:
    return UserSession(
        id=user_session.id,
        status=user_session.status.value,
        created_at=user_session.created_at,
        last_message=build_message(last_message) if last_message else None,
        total_messages=message_count,
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
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )
