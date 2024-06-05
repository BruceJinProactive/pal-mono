from typing import Callable, List, Optional

import streamlit as st
from phi.assistant import Assistant
from phi.document import Document
from phi.document.reader.pdf import PDFReader

from app.auth import user, user_ui
from utils.log import logger


def main_ui(get_assistant: Callable[[str, Optional[str]], Assistant]) -> None:
    # Get or create assistant
    assistant = get_assistant(
        user_id=user.username,
    )

    # Select or create run id
    assistant_run_ids: List[str] = assistant.storage.get_all_run_ids(
        user_id=user.username
    )
    if not st.session_state.get("new_run"):
        run_id = assistant_run_ids[0] if assistant_run_ids else None
        assistant.run_id = run_id
        st.session_state["new_run"] = False

    def new_run():
        st.session_state["new_run"] = True
        st.session_state["messages"] = []
        st.rerun()

    if st.sidebar.button("New Run"):
        new_run()

    # Load existing or create new run
    assistant_run_id = assistant.create_run()
    st.write(f"Run ID: {assistant_run_id}")

    # User UI
    user_ui()

    # Messaging UI
    messaging_ui(assistant)

    # Settings UI
    memory_ui(assistant)
    knowledge_base_ui(assistant)
    storage_ui(assistant)


def messaging_ui(assistant: Assistant) -> None:
    assistant_chat_history = assistant.memory.get_chat_history()
    st.session_state["messages"] = assistant_chat_history
    if assistant_chat_history == []:
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


def knowledge_base_ui(assistant: Assistant) -> None:
    st.sidebar.write("## Knowledge Base")

    # Load knowlege base if not already loaded
    if assistant.knowledge_base and (
        "knowledge_base_loaded" not in st.session_state
        or not st.session_state["knowledge_base_loaded"]
    ):
        if not assistant.knowledge_base.exists():
            logger.info("Knowledge base does not exist")
            loading_container = st.sidebar.info("🧠 Loading knowledge base")
            assistant.knowledge_base.load()
            st.session_state["knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base loaded")
            loading_container.empty()

    if assistant.knowledge_base:
        if st.sidebar.button("Update Knowledge Base"):
            assistant.knowledge_base.load(recreate=False, upsert=True)
            st.session_state["knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base updated")

        if st.sidebar.button("Recreate Knowledge Base"):
            assistant.knowledge_base.load(recreate=True)
            st.session_state["knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base recreated")

        if st.sidebar.button("Clear Knowledge Base"):
            assistant.knowledge_base.vector_db.clear()
            st.session_state["knowledge_base_loaded"] = False
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


def memory_ui(assistant: Assistant) -> None:
    st.sidebar.write("## Memory")

    if assistant.memory.memories:
        for item in assistant.memory.memories:
            st.sidebar.warning(item.memory)


def storage_ui(assistant: Assistant) -> None:
    st.sidebar.write("## Storage")

    assistant.auto_rename_run()
    st.sidebar.success(assistant.run_name)
    if assistant.storage:
        st.sidebar.success(
            f"Number of chats: {len(assistant.memory.get_chat_history())}"
        )
