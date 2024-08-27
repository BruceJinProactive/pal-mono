import streamlit as st
from demo_template import demo_ui
from phi.assistant import Assistant
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.coffee_assistant import get_coffee_assistant
from ai.assistants.gym_assistant import get_gym_assistant, get_mindzero_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from app.auth import user
from app.shared import set_page_config
from db.session import get_db
from services.admin_service import get_account
from services.assistant_service import get_assistant
from services.user_service import get_user

set_page_config()

st.title("Demo")


def get_prd_assistant(
    user_id: str,
    new_run: bool = False,
) -> Assistant:
    db = next(get_db())
    account = get_account(db, account_name=user.account_name)

    if account is None:
        raise ValueError("Account not found")

    if not account.projects:
        raise ValueError("No projects found for this account")

    db_user = get_user(
        db,
        account_id=account.id,
        channel_platform="INTERNAL_APP",
        channel_identifier=user_id,
        create_new_user=True,
    )

    if not db_user:
        raise ValueError("User not found in db")

    assistant_id = account.projects[0].assistant_id
    assistant: Assistant = get_assistant(
        db,
        assistant_id=assistant_id,
        user_id=db_user.id,
        new_run=new_run,
    )
    return assistant


if user.is_logged_in:
    # account_name : demo assistant getter mapping
    demo_dict = {
        # PRD assistant
        "pal-test": get_prd_assistant,
        # Internal demos
        "coffee": get_coffee_assistant,
        "customer": get_coffee_assistant,
        # Customer demos
        "mindzero": get_gym_assistant,
        "pizzamyheart": get_pizza_assistant,
        "mindzerov2": get_mindzero_assistant,
    }

    if user.account_name == "proactiveailab" or user.account_name == "root":
        # Internal demo selection
        selected_account_name = st.sidebar.selectbox(
            "[Internal] Select a demo then reload", list(demo_dict.keys())
        )
        get_demo_assistant = demo_dict.get(selected_account_name)
    else:
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
