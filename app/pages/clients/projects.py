import json

import pandas as pd
import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import get_app_db, json_decode, universal_picker_ui
from services.account_service import get_account
from services.project_service import (
    create_project,
    delete_project,
    get_project,
    replace_project_channel_identifiers,
    replace_project_config,
    update_project_config,
)

st.title("Projects")

session = get_app_db()


def main() -> None:
    st.warning("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View")
        return

    account_name = st.session_state["account_name"]
    account = get_account(session, account_name)

    st.subheader("Create Project")
    if account and account.agents:
        new_project_name = st.text_input("New Project Name", key="new_project_name")

        agent_ids = [agent.id for agent in account.agents]
        agent_id = st.selectbox(
            "Select an agent",
            agent_ids,
            key="new_project_agent_id",
            index=agent_ids.index(account.agents[0].id),
        )

        if st.button("Create Project", key="create_project"):
            if agent_id:
                new_project = create_project(
                    session, new_project_name, account.id, agent_id
                )
                if new_project:
                    st.success("Successfully created a new project")
                    st.rerun()
                else:
                    st.error("Failed to create a new project")
            else:
                st.error("Please select an agent to assign to this project")
    else:
        st.error("No agents found for this account")
    st.write("---")

    project = (
        get_project(session, st.session_state["project_id"])
        if (account and st.session_state["project_id"])
        else None
    )

    if project is None:
        st.write("Project not found or no project selected")
    else:
        st.subheader("Project Update")

        st.write(
            ":orange-background[Please __double-check any modifications__ before submitting.]"
        )

        st.write(
            ":red[__Modify__] the channel identifiers. Please unfocus (click off or press enter) any cells before saving."
        )

        channel_identifiers = project.channel_identifiers or [":"]
        old_df = pd.DataFrame(
            [
                {"Channel": channel, "Identifier": identifier}
                for channel_identifier in channel_identifiers
                for channel, identifier in [channel_identifier.split(":")]
            ]
        )
        new_df = st.data_editor(old_df, num_rows="dynamic", use_container_width=True)

        if st.button("Save"):
            new_channel_identifiers = []
            for _, row in new_df.iterrows():
                channel = row.get("Channel")
                identifier = row.get("Identifier")
                if channel and identifier:
                    new_channel_identifiers.append(f"{channel}:{identifier}")

            replace_project_channel_identifiers(
                session,
                project_id=project.id,
                channel_identifiers=new_channel_identifiers,
            )
            st.success("Successfully updated the channel identifiers")

        st.divider()

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
                replace_config_json = json_decode(replace_config)
                if replace_config_json:
                    replace_project_config(
                        session,
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
                update_config_json = json_decode(update_config)
                if update_config_json:
                    update_project_config(
                        session,
                        project_id=project.id,
                        config=update_config_json,
                    )
                    st.success("Successfully updated the agent config")
                else:
                    st.error("Invalid JSON format")

        st.subheader("Project Config")
        st.json(project.raw_config)

        st.subheader("Project Database Information")
        st.write(project)

        st.divider()

        # Delete project
        st.subheader("Delete Project")
        st.write(":red[__Warning: This action is irreversible!__]")

        if st.button("Delete Project", key="delete_project"):
            if st.session_state.get("confirm_delete", False):
                delete_project(session, project.id)
                st.success("Project deleted successfully")
                st.session_state["confirm_delete"] = False
                st.rerun()
            else:
                st.session_state["confirm_delete"] = True
                st.warning(
                    "Are you sure you want to delete this project? Click the button again to confirm."
                )


if user.is_logged_in:
    universal_picker_ui(session)
    main()
else:
    switch_page("home")
