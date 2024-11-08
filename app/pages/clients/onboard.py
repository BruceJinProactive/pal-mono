import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from db.session import get_db
from services.account_service import create_account_with_defaults
from services.agent_service import replace_agent_config

st.title("Onboard")
db = next(get_db())


def main() -> None:
    st.write("---")

    with st.form("onboarding_form"):
        account_name = st.text_input("Account Name")
        brand_story = st.text_area("Brand Story")
        highlights = st.text_area("Highlights")
        faqs = st.text_area("FAQs")

        # create account and save config into assistant
        if st.form_submit_button("Save"):
            config = {
                "system_prompt": {
                    "character": {
                        "brand_story": brand_story,
                        "highlights": highlights,
                        "faqs": faqs,
                    }
                }
            }
            new_account = create_account_with_defaults(db, account_name)
            replace_agent_config(
                db,
                agent_id=new_account.assistants[0].id,
                config=config,
            )
            st.success("Successfully onboarded")


if user.is_logged_in:
    main()
else:
    switch_page("home")
