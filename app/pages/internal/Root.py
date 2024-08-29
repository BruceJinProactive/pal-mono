import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config
from db.repositories.account_repository import AccountRepository
from db.session import get_db
from services.admin_service import create_account_with_defaults

set_page_config()

st.title("[Root] Manage Clients' Accounts")

db = next(get_db())


def main() -> None:
    st.error("[WARNING] Operations on this page are irreversible.")
    st.write("---")

    account_tab, assistant_tab, project_tab = st.tabs(
        ["Account", "Assistant", "Project"]
    )

    with account_tab:
        account_tab_ui()
    with assistant_tab:
        assistant_tab_ui()
    with project_tab:
        project_tab_ui()


def account_tab_ui():
    if "account_name" in st.session_state:
        account_name = st.session_state["account_name"]
        account_repository = AccountRepository(db)
        account = account_repository.get_account(account_name)
        st.write(account)


def assistant_tab_ui():
    st.write("Assistant")


def project_tab_ui():
    st.write("Project")


def account_picker_ui():
    with st.sidebar:
        st.write("## Account Picker")

        account_name = st.text_input("Enter Account Name")
        if st.button("Get Account"):
            st.session_state["account_name"] = account_name
        if st.button("Create Account with Defaults"):
            account = create_account_with_defaults(db=db, account_name=account_name)
            st.write(account)
            for assistent in account.assistants:
                st.write(assistent)
            for project in account.projects:
                st.write(project)


if user.is_logged_in:
    main()
    account_picker_ui()

else:
    switch_page("home")
