import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_account
from db.session import get_db
from services.account_service import get_accounts
from services.admin_service import get_inbox_conversations

st.title("Dashboard")

db = next(get_db())


def navigate_accounts(account_name):
    if account_name != st.session_state.get("account_name"):
        set_account(account_name)
    st.switch_page("./pages/clients/accounts.py")


def main() -> None:
    st.write("---")
    accounts = get_accounts(db)
    st.metric(label="Active Accounts", value=len(accounts), delta="2")

    table_headers = ["Account", "Status", "Users", "Details"]
    for th, col in zip(table_headers, st.columns([1] * len(table_headers))):
        col.write(th)
    for acc in accounts:
        name_col, status_col, users_col, action_col = st.columns(
            [1] * len(table_headers)
        )

        name_col.write(acc.name)
        users_col.write(len(get_inbox_conversations(db, acc.id)))
        status_col.write("Existing")

        if action_col.button("View", key=acc.name):
            navigate_accounts(acc.name)


if user.is_logged_in:
    main()
else:
    switch_page("home")
