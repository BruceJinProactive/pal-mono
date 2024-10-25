import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import universal_picker_ui
from db.session import get_db
from services.account_service import create_account_with_defaults, get_account

st.title("Accounts")

db = next(get_db())


def main() -> None:
    st.error("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View")
        return
    account_name = st.session_state["account_name"]
    account = get_account(db, account_name)
    st.write(account)


def create_account_with_defaults_ui():
    with st.sidebar:
        st.divider()
        account_name = st.text_input("Enter Account Name")
        if st.button("Create Account with Defaults"):
            create_account_with_defaults(db=db, account_name=account_name)
            st.rerun()


if user.is_logged_in:
    universal_picker_ui(db)
    main()
    create_account_with_defaults_ui()
else:
    switch_page("home")
