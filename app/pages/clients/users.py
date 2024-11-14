import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import account_picker_ui, chat_render_toggle
from db.session import get_db
from services.account_service import get_account
from services.message_service import (
    get_conversations_by_user,
    get_messages_by_conversation,
)
from services.user_service import get_users_by_account_id

st.title("Users")

db = next(get_db())


def render_conversation(user_id) -> None:
    CHAT_HEIGHT = 500
    conversations = get_conversations_by_user(db, user_id)
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
                db, conversations[active_conversation].id
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
    account = get_account(db, st.session_state["account_name"])
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    account_id = account.id
    account_users = get_users_by_account_id(db, account_id)

    # display users table
    chat_render_toggle()
    table_headers = ["Identifier", "Channel", "Id", "Conversation"]
    col_widths = [2] + [1] * (len(table_headers) - 1)
    for th, col in zip(table_headers, st.columns(col_widths)):
        col.write(th)
    for account_user in account_users:
        channel_col, identifier_col, id_col, conversation_col = st.columns(col_widths)
        try:
            if account_user.channel_identifiers:
                channel, identifier = account_user.channel_identifiers[0].split(":")
            else:
                raise ValueError
        except ValueError:
            channel, identifier = "Unknown", "Unknown"
        channel_col.write(channel)
        identifier_col.write(identifier)
        id_col.write(account_user.id)

        if conversation_col.toggle("View", key=str(account_user.id)):
            render_conversation(account_user.id)


if user.is_logged_in:
    main()
    account_picker_ui(db)
else:
    switch_page("home")
