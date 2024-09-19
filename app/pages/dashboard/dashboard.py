import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user

st.title("Dashboard")


def main() -> None:
    st.write("---")
    st.metric(label="Active Accounts", value="12", delta="2")


if user.is_logged_in:
    main()
else:
    switch_page("home")
