from typing import Callable, List

import streamlit as st
from phi.assistant import Assistant
from phi.document import Document
from phi.document.reader.pdf import PDFReader

from app.auth import user
from app.shared import user_ui
from data_access_layer.dal_user_id import get_user_id_for_account_name_user_email
from utils.log import logger


def demo_ui(get_assistant: Callable[[str, bool], Assistant]) -> None:
    user_id = get_user_id_for_account_name_user_email(user.account_name, user.email)
    if st.session_state.get("restart_chat"):
        logger.info("Restarting chat")
        assistant = get_assistant(
            user_id=user_id,
            new_run=True,
        )
        assistant.memory.chat_history = []
        assistant.memory.llm_messages = []
        st.session_state["messages"] = []
    else:
        logger.info("Not restarting chat")
        assistant = get_assistant(
            user_id=user_id,
            new_run=False,
        )
    st.session_state["restart_chat"] = False

    # Debug UI
    if user.account_name == "proactiveailab" or user.account_name == "root":
        debug_ui(assistant)

    # Load existing or create new run
    assistant.create_run()

    # User UI
    user_ui()

    # Messaging UI
    messaging_ui(assistant)

    # Settings UI
    memory_ui(assistant)
    knowledge_base_ui(assistant)
    # storage_ui(assistant)


demo_system_prompt = ""


def debug_ui(assistant: Assistant):
    # System Prompt
    system_prompt_expander = st.expander("System Prompt")
    global demo_system_prompt
    demo_system_prompt = system_prompt_expander.text_area(
        "System Prompt",
        assistant.system_prompt,
        height=300,
        label_visibility="collapsed",
    )
    # Debug Info
    with st.expander("Debug Info"):
        st.info(f"Assistant Name: {assistant.name}")
        st.info(f"Run ID: {assistant.run_id}")
        assistant.show_tool_calls = st.toggle(
            "Show Tool Calls", assistant.show_tool_calls
        )

    # Restart chat
    def restart_chat():
        st.session_state["restart_chat"] = True
        st.rerun()

    if st.button("Restart Chat"):
        restart_chat()


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
        assistant.system_prompt = demo_system_prompt
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

    # Load knowledge base if not already loaded
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
