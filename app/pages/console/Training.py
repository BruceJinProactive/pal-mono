import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config, user_ui

set_page_config()

st.title("Training")


def main() -> None:
    st.write("---")
    st.write("## Knowledge Base")

    st.write("---")
    st.write("## Rules")

    st.write("---")
    st.write("## Escalation Policies")


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
