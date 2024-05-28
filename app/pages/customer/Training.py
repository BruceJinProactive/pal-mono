import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user, user_ui

st.set_page_config(
    page_title="Training",
    page_icon="📖",
)
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
