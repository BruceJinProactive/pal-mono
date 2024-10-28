import pandas as pd
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
    st.write(
        "Please click the checkbox in the leftmost column to navigate to that account"
    )
    accounts = get_accounts(db)
    df = pd.DataFrame(
        [
            {
                "Account": acc.name,
                "Status": "Active",
                "Active users": len(get_inbox_conversations(db, acc.id, max_age=5)),
                "Total users": len(get_inbox_conversations(db, acc.id)),
            }
            for acc in accounts
        ]
    )
    event = st.dataframe(
        df, on_select="rerun", selection_mode="single-row", use_container_width=True
    )
    # need this long check for pyright, which claims event["selection"]["rows"] is an invalid retrieval
    if (
        "selection" in event
        and "rows" in event["selection"]
        and len(event["selection"]["rows"])
    ):
        selected_row = event["selection"]["rows"][0]
        selected_account = df.iloc[selected_row]["Account"]
        navigate_accounts(selected_account)


if user.is_logged_in:
    main()
else:
    switch_page("home")
