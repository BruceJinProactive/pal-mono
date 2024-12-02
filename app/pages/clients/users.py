import pandas as pd
import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import account_picker_ui, chat_render_toggle, get_app_db
from services.account_service import get_account
from services.message_service import (
    get_conversations_by_user,
    get_messages_by_conversation,
)
from services.user_service import get_users_by_account_id

st.title("Users")

session = get_app_db()


def _render_conversation(user_id) -> None:
    CHAT_HEIGHT = 500
    conversations = get_conversations_by_user(session, user_id)
    if not conversations:
        st.write("No conversations found for this user")
        return
    active_conversation = 0
    if len(conversations) > 1:
        options = [str(conversation.created_at) for conversation in conversations]
        choice = str(
            st.selectbox(
                "Select conversation (by created time)",
                options,
                index=0,
            )
        )
        active_conversation = options.index(choice)
    with st.container(height=CHAT_HEIGHT):
        messages = [
            message.body
            for message in get_messages_by_conversation(
                session, conversations[active_conversation].id
            )
        ]
        if not messages:
            st.write("No messages in this conversation")
        for message in messages:
            with st.chat_message(message["author_type"]):
                st.session_state["chat_render_method"](message["text"]["body"])


def main() -> None:
    st.write("---")
    if "chat_render_method" not in st.session_state:
        st.session_state["chat_render_method"] = st.text
    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View Users")
        return

    # get users
    account = get_account(session, st.session_state["account_name"])
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    account_id = account.id
    account_users = get_users_by_account_id(session, account_id)

    # display users table
    chat_render_toggle()
    st.write("Click the checkbox in the leftmost column to view conversations")
    user_dicts = []
    for account_user in account_users:
        try:
            if account_user.channel_identifiers:
                channel, identifier = account_user.channel_identifiers[0].split(":")
            else:
                raise ValueError
        except ValueError:
            channel, identifier = "Unknown", "Unknown"
        id = account_user.id
        user_dicts.append(
            {
                "Channel": channel,
                "Identifier": identifier,
                "User ID": id,
            }
        )
    df = pd.DataFrame(user_dicts)

    event = st.dataframe(
        df, on_select="rerun", selection_mode="single-row", use_container_width=True
    )
    # need this long check for pyright, which flags event["selection"]["rows"] as an invalid retrieval
    if (
        "selection" in event
        and "rows" in event["selection"]
        and len(event["selection"]["rows"])
    ):
        selected_row = event["selection"]["rows"][0]
        selected_identifier = df.iloc[selected_row]["User ID"]
        _render_conversation(selected_identifier)


if user.is_logged_in:
    main()
    account_picker_ui(session)
else:
    switch_page("home")
