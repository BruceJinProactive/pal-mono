from datetime import datetime

from sqlalchemy.orm import Session

import db
from api.routes.admin import UserContext
from services import agent_service, project_service
from services.agent_service import AgentParams
from services.project_service import ProjectParams

DEFAULT_PROJECT_INDEX = "projects"
DEFAULT_AGENT_INDEX = "agents"


def get_knowledge_settings(
    session: Session,
    context: UserContext,
    target: db.Project | db.Agent,
    auto_create: bool = False,
):
    if isinstance(target, db.Project):
        return _get_project_knowledge_settings(session, context, target, auto_create)
    elif isinstance(target, db.Agent):
        return _get_agent_knowledge_settings(session, context, target, auto_create)
    else:
        raise ValueError(f"Unrecognized target type: {type(target)}")


def _get_project_knowledge_settings(
    session: Session,
    context: UserContext,
    target: db.Project,
    auto_create: bool = False,
):
    raw_config, missing, index_name, namespace = (
        _get_knowledge_settings_from_raw_config(
            raw_config=target.raw_config,
            account_name=target.account.name,
            default_index_name=DEFAULT_PROJECT_INDEX,
            default_namespace_prefix=target.name,
            auto_create=auto_create,
        )
    )
    if missing and auto_create:
        project_service.update_project(
            session, context, target.id, ProjectParams(raw_config=raw_config)
        )
    return index_name, namespace


def _get_agent_knowledge_settings(
    session: Session,
    context: UserContext,
    target: db.Agent,
    auto_create: bool = False,
):
    raw_config, missing, index_name, namespace = (
        _get_knowledge_settings_from_raw_config(
            raw_config=target.raw_config,
            account_name=target.account.name,
            default_index_name=DEFAULT_AGENT_INDEX,
            default_namespace_prefix=f"{target.account.name}_{target.name}",
            auto_create=auto_create,
        )
    )
    if missing and auto_create:
        agent_service.update_agent(
            session, context, target.id, AgentParams(raw_config=raw_config)
        )
    return index_name, namespace


def _get_knowledge_settings_from_raw_config(
    raw_config: dict,
    account_name: str,
    default_index_name: str,
    default_namespace_prefix: str,
    auto_create: bool = False,
):
    missing = False
    knowledge_config = raw_config.get("knowledge", {})
    settings = knowledge_config.get("settings", {})

    index_name = settings.get("index_name")
    if not index_name and auto_create:
        missing = True
        index_name = default_index_name

    namespace = settings.get("namespace")
    if not namespace and auto_create:
        missing = True
        today = datetime.now().strftime("%Y-%m-%d")
        namespace = f"{default_namespace_prefix}_{today}"

    if missing and auto_create:
        raw_config["knowledge"] = knowledge_config
        if not knowledge_config:
            knowledge_config["enabled"] = 1
            knowledge_config["provider"] = "llamaindex"
            knowledge_config["identifier"] = account_name
        knowledge_config["settings"] = settings
        settings["index_name"] = index_name
        settings["namespace"] = namespace
        settings["vector_store_modality"] = "text"
        settings["vector_store_provider"] = "pinecone"
    return raw_config, missing, index_name, namespace
