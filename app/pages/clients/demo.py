import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.pages.clients.demo_template import demo_ui
from db.session import get_db
from services.account_service import get_accounts

st.title("Demo")


def _construct_demo_dict():
    """
    Returns dictionary of account name to assistant id
    """
    demo_dict = {}
    db = next(get_db())
    accounts = get_accounts(db)

    for account in accounts:
        for assistant in account.assistants:
            demo_dict[account.name] = assistant.id

    return demo_dict


if user.is_logged_in:
    # account_name : demo assistant getter mapping

    demo_dict = _construct_demo_dict()

    # Internal demo selection
    selected_account_name = st.sidebar.selectbox(
        "Select a demo then reload", list(demo_dict.keys())
    )
    assistant_id = demo_dict.get(selected_account_name)

    demo_ui(assistant_id)
else:
    switch_page("home")
