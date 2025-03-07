import uuid
from datetime import timedelta

import streamlit as st
from sqlalchemy.exc import IntegrityError
from streamlit_extras.switch_page_button import switch_page

from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Channel,
    Extras,
    Message,
    Metadata,
    TextObject,
)
from app.auth import user
from app.shared import get_app_db
from services.account_service import create_account_with_defaults, get_account
from services.admin_service import get_conversation_messages, get_inbox_conversations
from services.message_service import get_chat_response
from services.relay_service import send_message
from utils.dttm import current_utc

st.title("Services")

session = get_app_db()

(
    message_service_tab,
    agent_service_tab,
    admin_service_tab,
    relay_service_tab,
) = st.tabs(["Message Service", "Agent Service", "Admin Service", "Relay Service"])


def main() -> None:
    with message_service_tab:
        st.write("### get_chat_response")

        sender_identifier: str | None = st.text_input("Sender Channel Identifier")
        recipient_identifier: str | None = st.text_input("Recipient Channel Identifier")
        channel: Channel | None = st.radio(
            label="Channel",
            options=[channel for channel in Channel],
            format_func=(lambda channel: channel.value),
            key="channel",
        )
        broker: Broker | None = st.radio(
            label="Broker",
            options=[broker for broker in Broker],
            format_func=(lambda broker: broker.value),
            key="broker",
        )
        text: str = st.text_area("Text")
        extras: Extras = Extras(escalated=st.checkbox("Escalated", key="extras"))

        if st.button("Get Chat Response"):
            if not channel:
                st.error(f"Could not get chat response. Channel is {channel}.")
                return

            input_message = Message(
                author_type=AuthorType.USER,
                sender_identifier=sender_identifier,
                recipient_identifier=recipient_identifier,
                text=TextObject(body=text),
                channel=channel,
                broker=broker,
                extras=extras,
                metadata=Metadata(),
            )
            output_message = get_chat_response(session, input_message)
            st.write(output_message.to_dict())

    with agent_service_tab:
        st.write("Agent Service")
    with admin_service_tab:
        st.write("### get_inbox_conversations")

        account_names = ["proactiveailab", "mindzero", "pizzamyheart"]
        accounts = []

        for name in account_names:
            try:
                accounts.append(create_account_with_defaults(session, name))
            except IntegrityError:  # account already exists
                account = get_account(session, name)

                if not account:
                    continue

                accounts.append(account)

        selected_account = st.selectbox(
            "Select Accounts",
            [f"{account.id} ({account.name})" for account in accounts],
            key="account_select",
        )

        # Streamlit reruns the entire script every time an interaction happens (button click), and temporary variables get reset.
        # To address the issue effectively, we refine the use of st.session_state to ensure that all relevant data is retained across reruns,
        # and update the UI controls only when necessary.
        # Initialize session state variables if not already present

        if "loaded_conversations" not in st.session_state:
            st.session_state.loaded_conversations = False

        if "conversations" not in st.session_state:
            st.session_state.conversations = []

        if "selected_conversation" not in st.session_state:
            st.session_state.selected_conversation = None

        # Button to load inbox conversations
        if st.button("Get Inbox Conversations"):
            if selected_account:
                account_id = selected_account.split()[0]
                _, conversations = get_inbox_conversations(
                    session, uuid.UUID(account_id), page=1, page_size=100
                )
                st.session_state.conversations = conversations
                st.session_state.loaded_conversations = (
                    True  # Set flag to True after loading
                )
                st.session_state.selected_conversation = (
                    None  # Reset selected conversation
                )

                st.write(st.session_state.conversations)

        # Check if conversations are loaded to display further UI elements
        if st.session_state.loaded_conversations:
            if st.session_state.conversations:
                st.write("### get_conversation_messages")
                conversation_details = [
                    f"{conv.id} - Last message: '{conv.last_message_text[:50]}'... ({conv.num_messages} messages)"
                    for conv in st.session_state.conversations
                ]
                st.session_state.selected_conversation = st.selectbox(
                    "Select Conversations", conversation_details, key="conv_select"
                )
                if st.button("Get Conversation Messages", key="msg_button"):
                    if st.session_state.selected_conversation and selected_account:
                        selected_conversation_id = (
                            st.session_state.selected_conversation.split()[0]
                        )
                        account_id = selected_account.split()[0]
                        messages = get_conversation_messages(
                            session,
                            uuid.UUID(account_id),
                            uuid.UUID(selected_conversation_id),
                        )
                        message_texts = [
                            (
                                message.body.get("text", {}).get("body", "")
                                if message.body is not None
                                else ""
                            )
                            for message in messages
                        ]
                        st.write(message_texts)
            else:
                st.write("No conversations found for this account.")

    with relay_service_tab:
        st.write("Relay Service")

        # Generates warning but works.
        sender_identifier = st.selectbox(
            "Sender Number",
            [
                "+14244859440 (proactiveailab)",
                "+14244705958 (mindzero)",
                "+14244680365 (pizzamyheart)",
            ],
        )

        if sender_identifier:
            sender_identifier = sender_identifier.split()[0]
        else:
            sender_identifier = "+14244859440"

        recipient_identifier = st.text_input("Recipient Number")

        text = st.text_input("Message")

        time_delta = st.number_input("Delay (seconds)", min_value=0, value=0)

        delivery_time = current_utc() + timedelta(seconds=time_delta)

        if st.button("Send Message"):
            message_to_send = Message(
                author_type=AuthorType.USER,
                sender_identifier=sender_identifier,
                recipient_identifier=recipient_identifier,
                text=TextObject(body=text),
                channel=Channel.SMS,
                broker=Broker.SENDBLUE,
                metadata=Metadata(),
            )
            status = send_message(message_to_send, delivery_time)
            st.json(status)


if user.is_logged_in:
    main()
else:
    switch_page("home")
