import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user, user_ui
from db.repositories.account_repository import AccountRepository
from db.session import get_db

st.set_page_config(
    page_title="Pal Root",
    page_icon=":exclamation:",
)
st.title("Pal Root")


def main() -> None:
    st.write("---")

    st.warning("[WARNING] Operations on this page are irreversible.")

    db = next(get_db())
    account_repository = AccountRepository(db)

    account_id = int(st.number_input("Enter Account ID", step=1))
    account_name = st.text_input("Enter Account Name")
    if st.button("Get Accounts"):
        accounts = account_repository.get_accounts()
        for account in accounts:
            st.write(account)
    if st.button("Get Account"):
        account = account_repository.get_account(account_id, account_name)
        st.write(account)
    if st.button("Update Account"):
        account = account_repository.update_account(account_id, account_name)
        st.write(account)
    if st.button("Delete Account"):
        account = account_repository.delete_account(account_id)
        st.write(account)
    if st.button("Create Account with Defaults"):
        account = account_repository.create_account_with_defaults(account_name)
        st.write(account)
        for project in account.projects:
            st.write(project)
            for assistent in project.assistants:
                st.write(assistent)


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
