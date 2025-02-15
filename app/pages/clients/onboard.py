import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import get_app_db
from services.account_service import create_account_with_defaults
from services.agent_service import replace_agent_config

st.title("Onboard")
session = get_app_db()


def main() -> None:
    st.write("---")

    with st.form("onboarding_form"):
        account_name = st.text_input("Account Name")

        # create account and save config into agent
        if st.form_submit_button("Create Account"):
            if not account_name:
                st.error("Account name is required")
                return

            config = {
                "name": "",
                "role": "",
                "system_prompt": "",
            }
            new_account = create_account_with_defaults(session, account_name)
            replace_agent_config(
                session,
                agent_id=new_account.agents[0].id,
                config=config,
            )
            st.success("Successfully onboarded")


if user.is_logged_in:
    main()
else:
    switch_page("home")
