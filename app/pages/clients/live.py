import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from api.schemas.message.message import (
    AuthorType,
    ChannelPlatform,
    Extras,
    Message,
    MessagingBroker,
    TextObject,
)
from app.auth import user
from app.pages.clients.accounts import account_picker_ui
from db.session import get_db
from services.account_service import get_account
from services.message_service import (
    get_chat_response,
    get_conversations_by_user,
    get_messages_by_conversation,
)
from services.user_service import get_user_by_channel

st.title("Live")

db = next(get_db())


def main() -> None:
    st.write("---")
    if "account_name" not in st.session_state:
        st.error("Please Select an Account to Chat")
        return

    # Fetch account, user, then convesation history
    account_name = st.session_state["account_name"]
    account = get_account(db, account_name)
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    db_user = get_user_by_channel(
        db=db,
        account_id=account.id,
        channel_platform=ChannelPlatform.INTERNAL_APP,
        channel_identifier=str(user.email),
        create_new_user=True,
    )
    if not db_user:
        raise ValueError("User not found in db")
    conversations = get_conversations_by_user(db, db_user.id)
    st.session_state["messages"] = (
        [
            message.body
            for message in get_messages_by_conversation(
                db=db, conversation_id=conversations[0].id
            )
        ]
        if conversations
        else []
    )

    # prompt user
    if prompt := st.chat_input():
        user_message = Message(
            author_type=AuthorType.USER,
            sender_channel_identifier=str(user.email),
            recipient_channel_identifier=account_name,
            channel_platform=ChannelPlatform.INTERNAL_APP,
            messaging_broker=MessagingBroker.WEB,
            text=TextObject(body=prompt),
            extras=Extras(),
        ).dict()
        st.session_state["messages"].append(user_message)

    # render messages
    for message in st.session_state["messages"]:
        with st.chat_message(message["author_type"]):
            st.write(message["text"]["body"])

    # generate response if last message is from user
    if (
        st.session_state["messages"]
        and st.session_state["messages"][-1]["author_type"] == AuthorType.USER.value
    ):
        with st.chat_message("assistant"):
            with st.spinner("Working..."):
                response_message = get_chat_response(
                    db=db, message=Message.from_dict(st.session_state["messages"][-1])
                ).dict()
            st.session_state["messages"].append(response_message)
            st.write(response_message["text"]["body"])


if user.is_logged_in:
    main()
    account_picker_ui()
else:
    switch_page("home")
