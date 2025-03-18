import db
from api.routes.utils import map_uri_to_s3_url
from api.schemas.admin.account import Account
from api.schemas.admin.agent import Agent
from api.schemas.admin.project import Project


def build_account(account: db.Account) -> Account:
    return Account(
        id=str(account.id),
        name=account.name,
        display_name=account.display_name or account.name,
        icon_url=map_uri_to_s3_url(account.icon_uri),
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
