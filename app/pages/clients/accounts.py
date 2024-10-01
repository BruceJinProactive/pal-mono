import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_account
from db.session import get_db
from services.account_service import (
    create_account_with_defaults,
    get_account,
    get_accounts,
)
from services.assistant_service import (
    get_assistant,
    replace_assistant_config,
    update_assistant_config,
)
from services.project_service import (
    get_project,
    replace_project_config,
    update_project_config,
)

st.title("Accounts")

db = next(get_db())


def main() -> None:
    st.error("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    account_tab, assistant_tab, project_tab = st.tabs(
        ["Account", "Assistant", "Project"]
    )

    with account_tab:
        account_tab_ui()
    with assistant_tab:
        assistant_tab_ui()
    with project_tab:
        project_tab_ui()


def account_tab_ui():
    if "account_name" in st.session_state:
        account_name = st.session_state["account_name"]
        account = get_account(db, account_name)
        st.write(account)


def _json_decode(json_string: str) -> dict:
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return {}


def assistant_tab_ui():
    if "account_name" in st.session_state:
        account_name = st.session_state["account_name"]
        account = get_account(db, account_name)
        assistant = get_assistant(db, account.assistants[0].id) if account else None

        if assistant is None:
            st.write("Assistant not found")
        else:
            st.subheader("Assistant Update")

            st.write(
                ":orange-background[Please __double-check any modifications__ before submitting.]"
            )

            unformatted_json = dict(assistant.raw_config)
            formatted_json = json.dumps(unformatted_json, indent=4, ensure_ascii=False)
            formatted_json_str = str(formatted_json)

            st.write(":red[__Replace__] the entire assistant config")

            with st.form(key="replace_assistant_config_form"):
                replace_config_expander = st.expander("Replace Assistant Config")
                replace_config = replace_config_expander.text_area(
                    "Replace Assistant Config",
                    value=formatted_json_str,
                    height=400,
                    label_visibility="collapsed",
                )

                # Submit button
                if st.form_submit_button(label="Submit"):
                    replace_config_json = _json_decode(replace_config)
                    if replace_config_json:
                        replace_assistant_config(
                            db,
                            assistant_id=assistant.id,
                            config=replace_config_json,
                        )
                        st.success("Successfully replaced the assistant config")
                    else:
                        st.error("Invalid JSON format")

            st.divider()

            st.write(":blue[__Update a key(s)__] in the assistant config")

            with st.form(key="update_assistant_config_form"):
                update_config_expander = st.expander("Update Assistant Config")
                update_config = update_config_expander.text_area(
                    "Update Assistant Config",
                    value=json.dumps({}),
                    height=400,
                    label_visibility="collapsed",
                )

                # Submit button
                if st.form_submit_button(label="Submit"):
                    update_config_json = _json_decode(update_config)
                    if update_config_json:
                        update_assistant_config(
                            db,
                            assistant_id=assistant.id,
                            config=update_config_json,
                        )
                        st.success("Successfully updated the assistant config")
                    else:
                        st.error("Invalid JSON format")

            st.divider()

            st.write(":blue[Update a __branding__ key(s)] in the assistant config")
            with st.form(key="update_branding_key"):
                update_config_expander = st.expander("Update branding Key")
                update_config = update_config_expander.text_area(
                    "Update branding Key",
                    value=json.dumps({}),
                    height=400,
                    label_visibility="collapsed",
                )
                if st.form_submit_button(label="Submit"):
                    update_config_json = _json_decode(update_config)
                    if update_config_json:
                        modified_config = assistant.raw_config
                        modified_config["branding"].update(update_config_json)
                        update_assistant_config(
                            db,
                            assistant_id=assistant.id,
                            config=modified_config,
                        )

                        st.success("Successfully updated the assistant config")

                    else:
                        st.error("Invalid JSON format")

            st.write(":blue[Update a __System Prompt__ key(s)] in the assistant config")
            with st.form(key="update_system_prompt_key"):
                update_config_expander = st.expander("Update System Prompt Key")
                update_config = update_config_expander.text_area(
                    "Update System Prompt Key",
                    value=json.dumps({}),
                    height=400,
                    label_visibility="collapsed",
                )
                if st.form_submit_button(label="Submit"):
                    update_config_json = _json_decode(update_config)
                    if update_config_json:
                        modified_config = assistant.raw_config
                        modified_config["system_prompt"].update(update_config_json)
                        update_assistant_config(
                            db,
                            assistant_id=assistant.id,
                            config=modified_config,
                        )
                        st.success("Successfully updated the assistant config")
                    else:
                        st.error("Invalid JSON format")
            st.subheader("Assistant Config")
            st.json(assistant.raw_config)

            st.subheader("Assistant Database Information")
            st.write(assistant)


def project_tab_ui():
    if "account_name" in st.session_state:
        account_name = st.session_state["account_name"]
        account = get_account(db, account_name)
        project = get_project(db, account.projects[0].id) if account else None

        if project is None:
            st.write("Project not found")
        else:
            st.subheader("Project Update")

            st.write(
                ":orange-background[Please __double-check any modifications__ before submitting.]"
            )

            unformatted_json = dict(project.raw_config)
            formatted_json = json.dumps(unformatted_json, indent=4, ensure_ascii=False)
            formatted_json_str = str(formatted_json)

            st.write(":red[__Replace__] the entire project config")

            with st.form(key="replace_project_config_form"):
                replace_config_expander = st.expander("Replace Project Config")
                replace_config = replace_config_expander.text_area(
                    "Replace Project Config",
                    value=formatted_json_str,
                    height=400,
                    label_visibility="collapsed",
                )

                # Submit button
                if st.form_submit_button(label="Submit"):
                    replace_config_json = _json_decode(replace_config)
                    if replace_config_json:
                        replace_project_config(
                            db,
                            project_id=project.id,
                            config=replace_config_json,
                        )
                        st.success("Successfully replaced the project config")
                    else:
                        st.error("Invalid JSON format")

            st.divider()

            st.write(":blue[__Update a key(s)__] in the project config")

            with st.form(key="update_project_config_form"):
                update_config_expander = st.expander("Update Project Config")
                update_config = update_config_expander.text_area(
                    "Update Project Config",
                    value=json.dumps({}),
                    height=400,
                    label_visibility="collapsed",
                )

                # Submit button
                if st.form_submit_button(label="Submit"):
                    update_config_json = _json_decode(update_config)
                    if update_config_json:
                        update_project_config(
                            db,
                            project_id=project.id,
                            config=update_config_json,
                        )
                        st.success("Successfully updated the assistant config")
                    else:
                        st.error("Invalid JSON format")

            st.subheader("Project Config")
            st.json(project.raw_config)

            st.subheader("Project Database Information")
            st.write(project)


def account_picker_ui():
    with st.sidebar:
        st.subheader("Account Picker")

        account_names = [account.name for account in get_accounts(db)]

        if "account_name" not in st.session_state:
            st.session_state["account_name"] = "proactiveailab"

        account_name = st.selectbox(
            "Select an account",
            account_names,
            index=account_names.index(st.session_state["account_name"]),
        )

        if account_name != st.session_state.get("account_name"):
            set_account(account_name)
            st.rerun()


def project_picker_ui():
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


def assistant_picker_ui():
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


def universal_picker_ui():
    account_picker_ui()
    project_picker_ui()
    assistant_picker_ui()


def create_account_with_defaults_ui():
    with st.sidebar:
        st.divider()
        account_name = st.text_input("Enter Account Name")
        if st.button("Create Account with Defaults"):
            create_account_with_defaults(db=db, account_name=account_name)
            st.rerun()


if user.is_logged_in:
    universal_picker_ui()
    main()
    create_account_with_defaults_ui()
else:
    switch_page("home")
