import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from api.schemas.message.message import AuthorType, Channel, Extras, Message, TextObject
from app.auth import user
from app.shared import (
    chat_render_toggle,
    clear_memory_ui,
    get_app_db,
    memory_ui,
    universal_picker_ui,
)
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


def main() -> str | None:
    st.write("---")
    if "chat_render_method" not in st.session_state:
        st.session_state["chat_render_method"] = st.text
    if "account_name" not in st.session_state:
        st.error("Please select an account to chat")
        return
    if (
        "project_name" not in st.session_state
        or st.session_state["project_name"] == "No Project"
    ):
        st.error("Please select a project to chat")
        return

    # Get agent
    account_name = st.session_state["account_name"]
    account = get_account(db, account_name)
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    project_name = st.session_state["project_name"]
    project = ProjectRepository(db).get_project_by_channel_identifier(
        f"{Channel.INTERNAL_APP.value}:{project_name}"
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
        chat_render_toggle()
    col1, col2, _, _ = st.columns([1] * 4)
    with col1:
        if st.button("Create new chat"):
            create_conversation(db, db_user.id)
            st.rerun()
    with col2:
        clear_memory_ui(account_name, str(db_user.id))

    # prompt user
    if prompt := st.chat_input():
        user_message = Message(
            author_type=AuthorType.USER,
            sender_identifier=str(user.email),
            recipient_identifier=project_name,
            channel=Channel.INTERNAL_APP,
            text=TextObject(body=prompt),
            extras=Extras(),
        ).dict()
        st.session_state["messages"].append(user_message)

    # render messages
    for message in st.session_state["messages"]:
        author_type = "assistant" if message["author_type"] == "agent" else "user"
        with st.chat_message(author_type):
            st.session_state["chat_render_method"](message["text"]["body"])

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
            st.session_state["chat_render_method"](response_message["text"]["body"])
    return str(db_user.id)


if user.is_logged_in:
    user_id = main()
    universal_picker_ui(db)
    if user_id:
        memory_ui(st.session_state.get("account_name", ""), user_id)
else:
    switch_page("home")
