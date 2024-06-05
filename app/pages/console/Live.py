import streamlit as st
from demo_template import demo_ui
from phi.assistant import Assistant
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config
from db.session import get_db
from services.admin_service import get_account
from services.chat_service import get_assistant
from utils.log import logger

set_page_config()

st.title("Live")


def get_current_assistant(
    user_id: str,
    new_run: bool = False,
) -> Assistant:
    db = next(get_db())
    account = get_account(db, account_name=user.account_name)
    assistant_id = account.projects[0].assistants[0].id

    assistant: Assistant = get_assistant(
        db,
        assistant_id=assistant_id,
        user_id=user_id,
        new_run=new_run,
    )
    logger.info(f"get_current_assistant Assistant: {assistant}")
    return assistant


if user.is_logged_in:
    demo_ui(
        get_current_assistant,
    )
else:
    switch_page("home")
