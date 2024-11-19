import streamlit as st
from streamlit_extras.switch_page_button import switch_page

import db
from app.auth import user
from app.shared import universal_picker_ui
from services.account_service import get_account

st.title("Accounts")

session = next(db.get_db())


def main() -> None:
    st.warning("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View")
        return
    account_name = st.session_state["account_name"]
    account = get_account(session, account_name)
    st.write(account)


if user.is_logged_in:
    universal_picker_ui(session)
    main()
else:
    switch_page("home")
