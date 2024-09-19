import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user

st.title("Live")


def main() -> None:
    st.write("---")


if user.is_logged_in:
    main()
else:
    switch_page("home")
