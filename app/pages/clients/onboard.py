import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import universal_picker_ui
from db.session import get_db

st.title("Onboard")
db = next(get_db())


def main() -> None:
    st.write("---")


if user.is_logged_in:
    main()
    universal_picker_ui(db)
else:
    switch_page("home")
