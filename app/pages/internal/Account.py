import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config, user_ui
from db.session import get_db
from services.account_service import get_account

set_page_config()

st.title("Account")


def main() -> None:
    st.write("---")
    st.write("## Cognito")
    st.write(user)

    st.write("---")
    st.write("## RDS")
    db = next(get_db())

    st.write("### Account")
    account = get_account(db, account_name=user.account_name)
    if account is not None:
        st.write(account)

        st.write("### Assistant")
        for assistant in account.assistants:
            st.write(assistant)

        st.write("### Project")
        for project in account.projects:
            st.write(project)


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
