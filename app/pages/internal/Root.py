import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from db.session import get_db
from services.account_service import create_account_with_defaults, get_account
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

st.title("[Root] Manage Clients' Accounts")

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

        account_name = st.text_input("Enter Account Name")
        if st.button("Get Account"):
            st.session_state["account_name"] = account_name
            st.rerun()  # rerun script

        if st.button("Create Account with Defaults"):
            account = create_account_with_defaults(db=db, account_name=account_name)
            st.write(account)
            for assistant in account.assistants:
                st.write(assistant)
            for project in account.projects:
                st.write(project)


if user.is_logged_in:
    main()
    account_picker_ui()

else:
    switch_page("home")
