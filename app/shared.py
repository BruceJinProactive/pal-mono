import json

import streamlit as st
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from services.account_service import get_account, get_accounts


def set_page_config():
    st.set_page_config(
        page_title="Proactive AI Lab",
        page_icon="https://media.licdn.com/dms/image/D560BAQG_oe45276rYQ/company-logo_100_100/0/1717434128276?e=1725494400&v=beta&t=IfK9h8vL1zMVN0eLsAqcDnCvxHmRJis0J1J_SsGcC4s",
    )


def set_account(session: Session, account_name: str) -> None:
    """
    Sets the account name into the steamlit state.
    Also sets the project name to the first project in the account.

    Args:
        session (Session): The database session.
        account_name (str): The name of the account.

    Returns:
        None
    """
    st.session_state["account_name"] = account_name
    account = get_account(session, account_name)
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    st.session_state["project_name"] = (
        account.projects[0].name if account.projects else "No Project"
    )
    st.session_state["project_id"] = (
        account.projects[0].id if account.projects else None
    )
    if "agent_id" in st.session_state:
        st.session_state.pop("agent_id")


def account_picker_ui(session: Session) -> None:
    with st.sidebar:
        st.subheader("Account Picker")

        account_names = [account.name for account in get_accounts(session)]

        account_name = st.selectbox(
            "Select an account",
            account_names,
            index=(
                account_names.index(st.session_state["account_name"])
                if "account_name" in st.session_state
                else None
            ),
        )

        if account_name and account_name != st.session_state.get("account_name"):
            set_account(session, account_name)
            st.rerun()


def project_picker_ui(session: Session) -> None:
    if "account_name" in st.session_state:
        account = get_account(session, st.session_state["account_name"])

        if account and account.projects:
            with st.sidebar:
                st.subheader("Project Picker")

                name_to_project = {
                    project.name: project for project in account.projects
                }

                project_names = [project.name for project in account.projects]
                project_names.append("No Project")

                if (
                    "project_name" not in st.session_state
                    or "project_id" not in st.session_state
                ):
                    st.session_state["project_name"] = account.projects[0].name
                    st.session_state["project_id"] = account.projects[0].id

                project_name = st.selectbox(
                    "Select a project",
                    project_names,
                    index=project_names.index(st.session_state["project_name"]),
                )

                if project_name and project_name != st.session_state["project_name"]:
                    st.session_state["project_name"] = project_name
                    st.session_state["project_id"] = (
                        name_to_project[project_name].id
                        if project_name != "No Project"
                        else None
                    )
                    if "agent_id" in st.session_state:
                        st.session_state.pop("agent_id")
                    if project_name != "No Project":
                        st.session_state["agent_id"] = name_to_project[
                            project_name
                        ].agent_id
                    st.rerun()


def agent_picker_ui(session: Session) -> None:
    if (
        "account_name" in st.session_state
        and "project_name" in st.session_state
        and st.session_state["project_name"] == "No Project"
    ):
        account = None
        for acc in get_accounts(session):
            if acc.name == st.session_state["account_name"]:
                account = acc
                break

        if account and account.agents:
            with st.sidebar:
                st.subheader("Agent Picker")

                # agents don't have names, just list all
                agent_ids = [agent.id for agent in account.agents]

                if "agent_id" not in st.session_state:
                    st.session_state["agent_id"] = account.agents[0].id

                agent_id = st.selectbox(
                    "Select an agent",
                    agent_ids,
                    index=agent_ids.index(st.session_state["agent_id"]),
                )

                if agent_id != st.session_state["agent_id"]:
                    st.session_state["agent_id"] = agent_id
                    st.rerun()


def universal_picker_ui(session: Session) -> None:
    account_picker_ui(session)
    project_picker_ui(session)
    agent_picker_ui(session)


def json_decode(json_string: str) -> dict:
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return {}


def get_app_db() -> Session:
    """
    Streamlit dependency to get a synchronous database session.

    Returns:
        Session: SQLAlchemy database session

    Raises:
        RuntimeError: If database connection fails
    """
    if "db" not in st.session_state:
        try:
            session = next(db.get_db(), None)
            if session is None:
                raise RuntimeError("Failed to establish database connection")
            st.session_state.db = session
        except Exception as e:
            st.error("Database connection error")
            raise RuntimeError(f"Failed to connect to database: {str(e)}")
    return st.session_state.db


async def get_app_db_async() -> AsyncSession:
    """
    Streamlit dependency to get an asynchronous database session.

    Returns:
        AsyncSession: SQLAlchemy async database session

    Raises:
        RuntimeError: If database connection fails
    """
    if "db_async" not in st.session_state:
        try:
            async_gen = db.get_db_async()
            session = await anext(async_gen, None)
            if session is None:
                raise RuntimeError("Failed to establish async database connection")
            st.session_state.db_async = session
        except Exception as e:
            st.error("Async database connection error")
            raise RuntimeError(f"Failed to connect to async database: {str(e)}")
    return st.session_state.db_async


def chat_render_toggle():
    def swap_render_method():
        st.session_state["chat_render_method"] = (
            st.write if st.session_state["chat_render_method"] == st.text else st.text
        )

    return st.toggle(
        "Render markdown",
        value=st.session_state["chat_render_method"] == st.write,
        on_change=swap_render_method,
    )
