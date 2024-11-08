import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import json_decode, universal_picker_ui
from db.session import get_db
from services.account_service import get_account
from services.agent_service import get_agent, replace_agent_config

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
    agent = get_agent(db, account.assistants[0].id) if account else None

    if agent is None:
        st.write("Agent not found")
    else:
        st.subheader("Agent Update")

        st.write(
            ":orange-background[Please __double-check any modifications__ before submitting.]"
        )

        unformatted_json = dict(agent.raw_config)
        formatted_json = json.dumps(unformatted_json, indent=4, ensure_ascii=False)
        formatted_json_str = str(formatted_json)

        st.write(":red[__Replace__] the entire agent config")

        with st.form(key="replace_agent_config_form"):
            replace_config_expander = st.expander("Replace Agent Config")
            replace_config = replace_config_expander.text_area(
                "Replace Agent Config",
                value=formatted_json_str,
                height=400,
                label_visibility="collapsed",
            )

            # Submit button
            if st.form_submit_button(label="Submit"):
                replace_config_json = json_decode(replace_config)
                if replace_config_json:
                    replace_agent_config(
                        db,
                        agent_id=agent.id,
                        config=replace_config_json,
                    )
                    st.success("Successfully replaced the agent config")
                else:
                    st.error("Invalid JSON format")

        st.divider()

        st.subheader("Agent Config")
        st.json(agent.raw_config)

        st.subheader("Agent Database Information")
        st.write(agent)


if user.is_logged_in:
    universal_picker_ui(db)
    main()
else:
    switch_page("home")
