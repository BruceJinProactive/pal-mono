import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from api.models.message import (
    AuthorType,
    ChannelPlatform,
    Extras,
    Message,
    MessagingBroker,
    TextObject,
)
from app.auth import user
from app.shared import set_page_config
from db.session import get_db
from services.message_service.message_service import get_chat_response

set_page_config()

st.title("Services")

db = next(get_db())

message_service_tab, assistant_service_tab = st.tabs(
    ["Message Service", "Assistant Service"]
)


def main() -> None:
    with message_service_tab:
        st.write("### get_chat_response")

        sender_channel_identifier = st.text_input("From Number")
        recipient_channel_identifier = st.selectbox(
            "To Number",
            [
                "+14244859440 (proactiveailab)",
                "+14244705958 (mindzero)",
                "+14244680365 (pizzamyheart)",
            ],
        )
        if recipient_channel_identifier:
            recipient_channel_identifier = recipient_channel_identifier.split()[0]
        text = st.text_input("Text")

        if st.button("Get Chat Response"):
            input_message = Message(
                author_type=AuthorType.USER,
                sender_channel_identifier=sender_channel_identifier,
                recipient_channel_identifier=recipient_channel_identifier
                or "+14244859440",
                text=TextObject(body=text),
                channel_platform=ChannelPlatform.SMS,
                messaging_broker=MessagingBroker.SENDBLUE,
                extras=Extras(),
            )
            output_message = get_chat_response(db, input_message)
            st.write(output_message.to_dict())

    with assistant_service_tab:
        st.write("Assistant Service")


if user.is_logged_in:
    main()
else:
    switch_page("home")
