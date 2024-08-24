import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config, user_ui
from db.repositories.account_repository import AccountRepository
from db.session import get_db
from services.admin_service import create_account_with_defaults

set_page_config()

st.title("Root")


def main() -> None:
    st.write("---")

    st.error("[WARNING] Operations on this page are irreversible.")

    db = next(get_db())
    account_repository = AccountRepository(db)

    account_name = st.text_input("Enter Account Name")
    if st.button("Get Accounts"):
        accounts = account_repository.get_accounts()
        for account in accounts:
            st.write(account)
    if st.button("Get Account"):
        account = account_repository.get_account(account_name)
        st.write(account)
    if st.button("Delete Account"):
        account = account_repository.delete_account(account_name)
        st.write(account)
    if st.button("Create Account with Defaults"):
        account = create_account_with_defaults(db=db, account_name=account_name)
        st.write(account)
        for assistent in account.assistants:
            st.write(assistent)
        for project in account.projects:
            st.write(project)


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
