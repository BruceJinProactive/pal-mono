import json

import pandas as pd
import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import json_decode, universal_picker_ui
from db.session import get_db
from services.account_service import get_account
from services.project_service import (
    get_project,
    replace_project_channel_identifiers,
    replace_project_config,
    update_project_config,
)

st.title("Projects")

db = next(get_db())


def main() -> None:
    st.warning("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View")
        return

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
                db,
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
                update_config_json = json_decode(update_config)
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


if user.is_logged_in:
    universal_picker_ui(db)
    main()
else:
    switch_page("home")
