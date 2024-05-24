import shared as shared
import streamlit as st
from auth import user
from streamlit_extras.switch_page_button import switch_page

from db.repositories.account_repository import AccountRepository
from db.session import get_db

st.set_page_config(
    page_title="Account",
    page_icon=":key:",
)
st.title("Account")


def main() -> None:
    st.write("---")
    st.write("## Cognito")
    st.write(user)

    st.write("---")
    st.write("## RDS")
    db = next(get_db())
    account_repository = AccountRepository(db)
    account = account_repository.get_account(account_name=user.account_name)
    st.write(account)
    for project in account.projects:
        st.write(project)
        for assistant in project.assistants:
            st.write(assistant)


if user.is_logged_in:
    main()
    shared.user_ui()
else:
    switch_page("home")
