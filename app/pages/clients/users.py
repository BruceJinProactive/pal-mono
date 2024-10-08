import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.pages.clients.accounts import universal_picker_ui
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
        messages = get_messages_by_conversation(
            db, conversations[active_conversation].id
        )
        if not messages:
            st.write("No messages in this conversation")
        for message in messages:
            body = message.body
            with st.chat_message(body["author_type"]):
                st.write(body["text"]["body"])


def main() -> None:
    st.write("---")

    account = get_account(db, st.session_state["account_name"])
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    account_id = account.id
    account_users = get_users_by_account_id(db, account_id)

    table_headers = ["Identifier", "Platform", "Id", "Conversation"]
    col_widths = [2] + [1] * (len(table_headers) - 1)
    for th, col in zip(table_headers, st.columns(col_widths)):
        col.write(th)
    for account_user in account_users:
        identifier_col, platform_col, id_col, conversation_col = st.columns(col_widths)
        identifier_col.write(account_user.raw_config["channel_identifier"])
        platform_col.write(account_user.raw_config["channel_platform"])
        id_col.write(account_user.id)

        if conversation_col.toggle("View", key=str(account_user.id)):
            render_conversation(account_user.id)


if user.is_logged_in:
    universal_picker_ui()
    main()
else:
    switch_page("home")
