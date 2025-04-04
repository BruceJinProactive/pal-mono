import time

import pandas as pd
import streamlit as st
from streamlit_extras.switch_page_button import switch_page

import db
from api.schemas.chat.message import (
    AuthorType,
    Channel,
    Extras,
    Message,
    Metadata,
    TextObject,
)
from app.auth import user
from app.shared import get_app_db, universal_picker_ui
from services.account_service import get_account
from services.message_service import create_conversation, get_chat_response
from services.user_service import get_user_by_channel_identifier

st.title("Test")
session = get_app_db()
TEST_USER = "test@proactiveailab.com"
# Initialize predefined inputs and expected outputs in session state
if "predefined_inputs" not in st.session_state:
    st.session_state["predefined_inputs"] = []

if "expected_outputs" not in st.session_state:
    st.session_state["expected_outputs"] = []

if "response_blocks" not in st.session_state:
    st.session_state["response_blocks"] = []


def main() -> str | None:
    st.write("---")
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
    account = get_account(session, account_name)
    if not account:
        raise ValueError(
            "There was an error accessing account details. Please reselect from picker"
        )
    project_name = st.session_state["project_name"]
    project = db.ProjectRepository(session).get_project_by_channel_identifier(
        f"{Channel.INTERNAL_APP.value}:{project_name}"
    )
    if not project:
        raise ValueError(
            "Account has no associated project. Please ensure the internal_app channel identifier is set up."
        )

    # Get conversation
    channel_identifier = f"{Channel.INTERNAL_APP.value}:{TEST_USER}"
    db_user = get_user_by_channel_identifier(
        session=session,
        account_id=account.id,
        channel_identifier=channel_identifier,
        create_new_user=True,
    )
    if not db_user:
        raise ValueError("User not found in db")

    # Excel uploader
    st.subheader("Upload Test Cases")
    st.warning("Please upload an Excel file with 'input' and 'expected_output' columns")
    uploaded_file = st.file_uploader(
        "Upload Excel file with 'input' and 'expected_output' columns", type=["xlsx"]
    )
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, engine="openpyxl")
            if "input" in df.columns and "expected_output" in df.columns:
                # Replace existing test cases with uploaded ones
                st.session_state["predefined_inputs"] = [
                    str(input_value).strip()
                    for input_value in df["input"].fillna("").tolist()
                    if str(input_value).strip()
                ]
                st.session_state["expected_outputs"] = [
                    str(output_value).strip()
                    for output_value in df["expected_output"].fillna("").tolist()
                    if str(output_value).strip()
                ]
                st.success("Test cases loaded successfully and replaced existing ones!")
        except Exception as e:
            st.error(f"Error reading Excel file: {e}")
    # Layout for Predefined Inputs and Expected Outputs
    st.subheader("Test Cases")
    col1, col2 = st.columns(2)
    with col1:
        predefined_inputs = st.text_area(
            "Modify the input lines below (one line per message):",
            value="\n\n".join(st.session_state["predefined_inputs"]),
            height=200,
        )
        # Split the inputs by double newlines and filter out empty strings
        new_inputs = [
            input_value.strip()
            for input_value in predefined_inputs.split("\n\n")
            if input_value.strip()
        ]
        st.session_state["predefined_inputs"] = new_inputs

    with col2:
        expected_outputs = st.text_area(
            "Modify the expected outputs below (one line per message):",
            value="\n\n".join(st.session_state["expected_outputs"]),
            height=200,
        )
        # Split the outputs by double newlines and filter out empty strings
        new_outputs = [
            output_value.strip()
            for output_value in expected_outputs.split("\n\n")
            if output_value.strip()
        ]
        st.session_state["expected_outputs"] = new_outputs

    _, col2, _, _ = st.columns([1] * 4)
    with col2:
        # Process predefined inputs as a batch and render as blocks
        if st.button("Run Automation"):
            create_conversation(
                session=session,
                user_id=db_user.id,
            )
            st.session_state["response_blocks"] = []  # Reset response blocks
            for idx, prompt in enumerate(st.session_state["predefined_inputs"]):
                if prompt.strip():  # Skip empty inputs
                    # User message
                    user_message = Message(
                        author_type=AuthorType.USER,
                        sender_identifier=TEST_USER,
                        recipient_identifier=project_name,
                        channel=Channel.INTERNAL_APP,
                        text=TextObject(body=prompt),
                        extras=Extras(),
                        metadata=Metadata(),
                    ).dict()

                    # Get agent response
                    response_message_text = get_chat_response(
                        session=session,
                        message=Message.from_dict(user_message),
                    ).text
                    if not response_message_text:
                        response_message = "No response from agent"
                    else:
                        response_message = response_message_text.body

                    # Append to response blocks
                    expected_output = (
                        st.session_state["expected_outputs"][idx]
                        if idx < len(st.session_state["expected_outputs"])
                        else "No expected output provided"
                    )
                    st.session_state["response_blocks"].append(
                        {
                            "user": prompt,
                            "expected": expected_output,
                            "agent": response_message,
                        }
                    )
                    time.sleep(1)  # Simulate delay for UX

    # Display responses as blocks
    st.write("### Test Results")
    for block in st.session_state["response_blocks"]:
        with st.expander(f"User Input: {block['user']}"):
            st.markdown(f"**Agent Response:** {block['agent']}")
            st.markdown(f"**Expected Output:** {block['expected']}")
    return str(db_user.id)


if user.is_logged_in:
    user_id = main()
    universal_picker_ui(session)
else:
    switch_page("home")
