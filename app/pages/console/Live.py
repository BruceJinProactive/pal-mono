from typing import List

import streamlit as st
from phi.assistant import Assistant
from phi.document import Document
from phi.document.reader.pdf import PDFReader
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import set_page_config, user_ui
from db.session import get_db
from services.admin_service import get_account
from services.chat_service import get_assistant
from utils.log import logger

set_page_config()

st.title("Live")


def main() -> None:
    db = next(get_db())

    # Get the assistant
    account = get_account(db, account_name=user.account_name)
    assistant_id = account.projects[0].assistants[0].id
    assistant: Assistant = get_assistant(
        db,
        assistant_id=assistant_id,
        user_id=user.username,
    )

    # Get the run id
    assistant_run_ids: List[str] = assistant.storage.get_all_run_ids(
        user_id=user.username
    )
    assistant_run_id = None
    if not assistant_run_ids or len(assistant_run_ids) == 0:
        assistant_run_id = assistant.create_run()
    else:
        assistant_run_id = assistant_run_ids[0]
    assistant.run_id = assistant_run_id

    st.session_state["coffee_assistant_run_id"] = assistant.create_run()

    # Load messages for existing assistant
    assistant_chat_history = assistant.memory.get_chat_history()
    if len(assistant_chat_history) > 0:
        logger.debug("Loading chat history")
        st.session_state["messages"] = assistant_chat_history
    else:
        logger.debug("No chat history found")
        st.session_state["messages"] = [
            {"role": "assistant", "content": "Ask me anything..."}
        ]

    # Prompt for user input
    if prompt := st.chat_input():
        st.session_state["messages"].append({"role": "user", "content": prompt})

    # Display existing chat messages
    for message in st.session_state["messages"]:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # If last message is from a user, generate a new response
    last_message = st.session_state["messages"][-1]
    if last_message.get("role") == "user":
        question = last_message["content"]
        with st.chat_message("assistant"):
            with st.spinner("Working..."):
                response = ""
                resp_container = st.empty()
                for delta in assistant.run(question, stream=False):
                    response += delta  # type: ignore
                    resp_container.markdown(response)

            st.session_state["messages"].append(
                {"role": "assistant", "content": response}
            )

    if assistant.knowledge_base:
        st.sidebar.write("## Knowledge Base")
        if st.sidebar.button("Update Knowledge Base"):
            assistant.knowledge_base.load(recreate=False, upsert=True)
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base updated")

        if st.sidebar.button("Recreate Knowledge Base"):
            assistant.knowledge_base.load(recreate=True)
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base recreated")

        if st.sidebar.button("Clear Knowledge Base"):
            assistant.knowledge_base.vector_db.clear()
            st.session_state["pdf_knowledge_base_loaded"] = False
            st.sidebar.success("Knowledge base cleared")

    # Upload PDF
    if assistant.knowledge_base:
        if "file_uploader_key" not in st.session_state:
            st.session_state["file_uploader_key"] = 0

        uploaded_file = st.sidebar.file_uploader(
            "Upload PDF",
            type="pdf",
            key=st.session_state["file_uploader_key"],
        )
        if uploaded_file is not None:
            alert = st.sidebar.info("Processing PDF...", icon="ℹ️")
            pdf_name = uploaded_file.name.split(".")[0]
            if f"{pdf_name}_uploaded" not in st.session_state:
                reader = PDFReader()
                pdf_documents: List[Document] = reader.read(uploaded_file)
                if pdf_documents:
                    assistant.knowledge_base.load_documents(pdf_documents)
                else:
                    st.sidebar.error("Could not read PDF")
                st.session_state[f"{pdf_name}_uploaded"] = True
            alert.empty()


if user.is_logged_in:
    user_ui()
    main()
else:
    switch_page("home")
