import json

import streamlit as st
from sqlalchemy.orm import Session

from services.account_service import get_accounts


def set_page_config():
    st.set_page_config(
        page_title="Proactive AI Lab",
        page_icon="https://media.licdn.com/dms/image/D560BAQG_oe45276rYQ/company-logo_100_100/0/1717434128276?e=1725494400&v=beta&t=IfK9h8vL1zMVN0eLsAqcDnCvxHmRJis0J1J_SsGcC4s",
    )


def set_account(account_name):
    st.session_state["account_name"] = account_name
    if "project_name" in st.session_state:
        st.session_state.pop("project_name")
    if "assistant_id" in st.session_state:
        st.session_state.pop("assistant_id")


def footer_ui():
    footer = """
        <style>
        .sidebar .sidebar-content {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
        }
        .footer {
            text-align: center;
            padding: 10px 0;
            font-size: 12px;
            color: gray;
        }
        </style>
        <div class="footer">
            <hr>
            <p>© 2024 Proactive AI Lab</p>
        </div>
        """

    st.sidebar.markdown(footer, unsafe_allow_html=True)


def account_picker_ui(db: Session) -> None:
    with st.sidebar:
        st.subheader("Account Picker")

        account_names = [account.name for account in get_accounts(db)]

        account_name = st.selectbox(
            "Select an account",
            account_names,
            index=(
                account_names.index(st.session_state["account_name"])
                if "account_name" in st.session_state
                else None
            ),
        )

        if account_name != st.session_state.get("account_name"):
            set_account(account_name)
            st.rerun()


def project_picker_ui(db: Session) -> None:
    if "account_name" in st.session_state:

        account = None
        for acc in get_accounts(db):
            if acc.name == st.session_state["account_name"]:
                account = acc
                break

        if account and account.projects:
            with st.sidebar:
                st.subheader("Project Picker")

                name_to_project = {}
                for project in account.projects:
                    name_to_project[project.name] = project

                project_names = [project.name for project in account.projects]
                project_names.append("No Project")

                if "project_name" not in st.session_state:
                    st.session_state["project_name"] = account.projects[0].name

                project_name = st.selectbox(
                    "Select a project",
                    project_names,
                    index=project_names.index(st.session_state["project_name"]),
                )

                if project_name != st.session_state["project_name"]:
                    st.session_state["project_name"] = project_name
                    if "assistant_id" in st.session_state:
                        st.session_state.pop("assistant_id")
                    if project_name != "No Project":
                        st.session_state["assistant_id"] = name_to_project[
                            project_name
                        ].assistant_id


def assistant_picker_ui(db: Session) -> None:
    if (
        "account_name" in st.session_state
        and "project_name" in st.session_state
        and st.session_state["project_name"] == "No Project"
    ):

        account = None
        for acc in get_accounts(db):
            if acc.name == st.session_state["account_name"]:
                account = acc
                break

        if account and account.assistants:
            with st.sidebar:
                st.subheader("Assistant Picker")

                # assistants don't have names, just list all
                assistant_ids = []
                for assistant in account.assistants:
                    assistant_ids.append(assistant.id)

                if "assistant_id" not in st.session_state:
                    st.session_state["assistant_id"] = account.assistants[0].id

                assistant_id = st.selectbox(
                    "Select an assistant",
                    assistant_ids,
                    index=assistant_ids.index(st.session_state["assistant_id"]),
                )

                if assistant_id != st.session_state["assistant_id"]:
                    st.session_state["assistant_id"] = assistant_id
                    st.rerun()


def universal_picker_ui(db: Session) -> None:
    account_picker_ui(db)
    project_picker_ui(db)
    assistant_picker_ui(db)


def json_decode(json_string: str) -> dict:
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return {}
