import streamlit as st
from demo_template import demo_ui
from phi.assistant import Assistant
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.coffee_assistant import get_coffee_assistant
from ai.assistants.gym_assistant import get_gym_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from app.auth import user
from app.shared import set_page_config
from db.session import get_db
from services.admin_service import get_account
from services.chat_service import get_assistant

set_page_config()

st.title("Live")


def get_prd_assistant(
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
    return assistant


if user.is_logged_in:
    # account_name : demo assistant getter mapping
    demo_dict = {
        # Internal demos
        "☕ coffee": get_coffee_assistant,
        # Customer demos
        "🏋️ mindzero": get_gym_assistant,
        "🍕 pizzamyheart": get_pizza_assistant,
    }

    # Internal demo selection
    if user.account_name == "proactiveailab" or user.account_name == "root":
        selected_account_name = st.sidebar.selectbox(
            "[Internal] Select a demo", demo_dict.keys()
        )
        get_demo_assistant = demo_dict.get(selected_account_name)

    # Select customer demo
    get_demo_assistant = demo_dict.get(user.account_name)
    # If no demo availalbe, use the prd assistant
    if get_demo_assistant is None:
        get_demo_assistant = get_prd_assistant

    demo_ui(
        get_demo_assistant,
    )
else:
    switch_page("home")
