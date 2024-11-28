import json
from uuid import uuid4

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from ai.tools.booking_tools import BookingTools
from ai.tools.ordering_tools import OrderingTools
from api.schemas.chat.message import Channel
from app.auth import user
from app.shared import get_app_db
from services.account_service import get_account, get_accounts
from services.agent_service import get_agent
from services.user_service import get_user_by_channel_identifier
from utils.secret import get_client_secret

st.title("Tools")

session = get_app_db()

(ordering_tools_tab, booking_tools_tab) = st.tabs(["Ordering Tools", "Booking Tools"])


def ordering_tools_tab_content(user_id):
    st.write("# Ordering Tools")
    toolkit = OrderingTools(
        {
            "type": "adora",
            "settings": {
                "api_key": get_client_secret("PIZZAMYHEART_ADORA_API_KEY"),
                "api_secret": get_client_secret("PIZZAMYHEART_ADORA_API_SECRET"),
                "store_id": "9WHCV",  # obsolete
                "menu_name": "Pizza_My_Heart_Adora_Menu",  # obsolete
                "account_name": "pizzamyheart",
                "store_information": {
                    "phone": "650-327-9400",
                    "address": "220 University Ave, Palo Alto, CA 94301",
                    "store_id": "9WHCV",
                },
            },
        },
        user_id=user_id,
        session_id=str(uuid4()),
    )

    st.write("### Add to Order")
    item_name = st.text_input("Item Name", value="Big Sur")
    size = st.text_input("Size", value='18"')
    quantity = st.number_input("Quantity", value=1)
    modifications = st.text_input(
        "Modifications", value="Extra Garlic, Light Mushrooms", help="Separate by comma"
    )
    if st.button("Add to Order"):
        try:
            retval = toolkit.add_to_order(
                item_name,
                size,
                int(quantity),
                str(modifications).split(","),
            )
            st.write(retval)
        except Exception as e:
            st.error(f"Failed to add to order: {e}")

    st.write("### Place Order")
    if st.button("Place Order"):
        try:
            retval = toolkit.place_order(
                current_user_query="my name is John Doe. My email is 123@abc.com and my phone number is 123-456-7890. "
                + f"add {quantity} {size} {item_name} with {modifications} to cart. "
                + "when I place order, do pickup."
            )
            st.write(retval)
        except Exception as e:
            st.error(f"Failed to place order: {e}")


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
    with ordering_tools_tab:
        ordering_tools_tab_content(user_id)
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
