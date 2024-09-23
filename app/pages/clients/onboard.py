import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.pages.clients.accounts import universal_picker_ui

st.title("Onboard")


def main() -> None:
    st.write("---")


if user.is_logged_in:
    main()
    universal_picker_ui()
else:
    switch_page("home")
