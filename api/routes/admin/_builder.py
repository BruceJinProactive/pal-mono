import db
from api.routes.utils import map_uri_to_s3_url
from api.schemas.admin.account import Account
from api.schemas.admin.agent import Agent
from api.schemas.admin.conversation import Message, UserSession
from api.schemas.admin.feedback import Feedback
from api.schemas.admin.project import Project


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
        agent_type=agent.raw_config.get("agent_type"),
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
