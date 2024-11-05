import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import json_decode, universal_picker_ui
from db.session import get_db
from services.account_service import get_account
from services.assistant_service import (
    get_assistant,
    replace_assistant_config,
    update_assistant_config,
)

st.title("Agents")

db = next(get_db())


def main() -> None:
    st.warning("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View")
        return

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
                replace_config_json = json_decode(replace_config)
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
                update_config_json = json_decode(update_config)
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
                update_config_json = json_decode(update_config)
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
                update_config_json = json_decode(update_config)
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


if user.is_logged_in:
    universal_picker_ui(db)
    main()
else:
    switch_page("home")
