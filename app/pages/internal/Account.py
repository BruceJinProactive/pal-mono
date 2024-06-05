import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config, user_ui
from db.session import get_db
from services.admin_service import get_account

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
    st.write(account)
    st.write("### Project")
    for project in account.projects:
        st.write(project)
        st.write("### Assistant")
        for assistant in project.assistants:
            st.write(assistant)


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
