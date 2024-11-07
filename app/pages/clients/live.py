import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from api.schemas.message.message import AuthorType, Channel, Extras, Message, TextObject
from app.auth import user
from app.shared import account_picker_ui, get_app_db
from db.repositories.project_repository import ProjectRepository
from services.account_service import get_account
from services.message_service import (
    create_conversation,
    get_chat_response,
    get_conversations_by_user,
    get_messages_by_conversation,
)
from services.user_service import get_user_by_channel_identifier

st.title("Live")

db = get_app_db()


def main() -> None:
    st.write("---")
    if "account_name" not in st.session_state:
        st.error("Please Select an Account to Chat")
        return

    # Get agent
    account_name = st.session_state["account_name"]
    account = get_account(db, account_name)
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    project = ProjectRepository(db).get_project_by_channel_identifier(
        f"{Channel.INTERNAL_APP.value}:{account_name}"
    )
    if not project:
        raise ValueError(
            "Account has no associated project. Please ensure the internal_app channel identifier is set up."
        )
    assistant = project.assistant

    # Get conversation
    channel_identifier = f"{Channel.INTERNAL_APP.value}:{str(user.email)}"
    db_user = get_user_by_channel_identifier(
        db=db,
        account_id=account.id,
        channel_identifier=channel_identifier,
        create_new_user=True,
    )
    if not db_user:
        raise ValueError("User not found in db")
    conversations = get_conversations_by_user(db, db_user.id)
    conversation = conversations[-1] if conversations else None
    st.session_state["messages"] = (
        [
            message.body
            for message in get_messages_by_conversation(
                db=db, conversation_id=conversation.id
            )
        ]
        if conversation
        else []
    )

    # Debug Info
    with st.expander("System Prompt"):
        st.text_area(
            "System Prompt",
            json.dumps(assistant.raw_config, indent=4),
            height=300,
            label_visibility="collapsed",
        )
    with st.expander("Debug Info"):
        assistant_name = (
            assistant.raw_config.get("system_prompt", {})
            .get("character", {})
            .get("name", "None")
        )
        st.info(f"Assistant Name: {assistant_name}")
        st.info(f"Conversation start date: {getattr(conversation, 'created_at', None)}")
    col1, _, _, _ = st.columns([1] * 4)
    with col1:
        if st.button("Create new chat"):
            create_conversation(db, db_user.id)
            st.rerun()

    # prompt user
    if prompt := st.chat_input():
        user_message = Message(
            author_type=AuthorType.USER,
            sender_identifier=str(user.email),
            recipient_identifier=account_name,
            channel=Channel.INTERNAL_APP,
            text=TextObject(body=prompt),
            extras=Extras(),
        ).dict()
        st.session_state["messages"].append(user_message)

    # render messages
    for message in st.session_state["messages"]:
        author_type = "assistant" if message["author_type"] == "agent" else "user"
        with st.chat_message(author_type):
            st.text(message["text"]["body"])

    # generate response if last message is from user
    if (
        st.session_state["messages"]
        and st.session_state["messages"][-1]["author_type"] == AuthorType.USER.value
    ):
        with st.chat_message("assistant"):
            with st.spinner("Working..."):
                response_message = get_chat_response(
                    db=db,
                    message=Message.from_dict(st.session_state["messages"][-1]),
                ).dict()
            st.session_state["messages"].append(response_message)
            st.text(response_message["text"]["body"])


if user.is_logged_in:
    main()
    account_picker_ui(db)
else:
    switch_page("home")
