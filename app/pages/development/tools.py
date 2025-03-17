# Temporarily disble specific pyright errors since Datadog annotations are not fully compatible with pyright yet.
# pyright: reportCallIssue=false, reportReturnType=false, reportArgumentType=false

import json
from uuid import uuid4

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from api.schemas.chat.message import Channel
from app.auth import user
from app.shared import get_app_db
from services.account_service import get_account, get_accounts
from services.agent_service import get_agent
from services.user_service import get_user_by_channel_identifier
from tools.legacy.booking_tools import BookingTools

st.title("Tools")

session = get_app_db()

(ordering_tools_tab, booking_tools_tab) = st.tabs(["Ordering Tools", "Booking Tools"])


def booking_tools_tab_content(user_id):
    st.write("# Booking Tools")
    toolkit = BookingTools(
        {"type": "mindzero", "settings": {}}, user_id=user_id, session_id=uuid4()
    )

    st.write("### Get Class Sessions")
    num_days = st.number_input("Number of Days", value=7)
    if st.button("Get Class Sessions"):
        try:
            retval = toolkit.get_classes(int(num_days))
            st.json(json.loads(retval))
        except Exception as e:
            st.error(f"Failed to get class sessions: {e}")


# TODO: Delete this function
def _construct_demo_dict():
    """
    Returns dictionary of account name to agent id
    """
    demo_dict = {}
    session = get_app_db()
    accounts = get_accounts(session)

    for account in accounts:
        for agent in account.agents:
            demo_dict[account.name] = agent.id

    return demo_dict


def main(user_id) -> None:
    with booking_tools_tab:
        booking_tools_tab_content(user_id)


if user.is_logged_in:
    demo_dict = _construct_demo_dict()

    # Internal demo selection
    selected_account_name = st.sidebar.selectbox(
        "Select a demo then reload",
        list(demo_dict.keys()),
        key="tools_page_demo_select",
    )
    agent_id = demo_dict.get(selected_account_name)

    agent = get_agent(session, agent_id)  # type: ignore

    account = get_account(session, account_name=agent.account.name)  # type: ignore

    if not user.email:
        st.error("Email is required, please provide an email address.")
        st.stop()

    db_user = get_user_by_channel_identifier(
        session,
        account_id=account.id,  # type: ignore
        channel_identifier=f"{Channel.INTERNAL_APP.value}:{user.email}",
        create_new_user=True,
    )

    if db_user:
        main(db_user.id)
    else:
        st.write("Failed to get user")
else:
    switch_page("home")
