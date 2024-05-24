from typing import List

import streamlit as st
from phi.assistant import Assistant
from phi.document import Document
from phi.document.reader.pdf import PDFReader
from phi.tools.streamlit.components import (
    get_openai_key_sidebar,
    get_username_sidebar,
)

from ai.assistants.coffee_assistant import get_coffee_assistant
from utils.log import logger

st.set_page_config(
    page_title="Max's Coffee",
    page_icon=":coffee:",
)
st.title("Max's Coffee")


def main() -> None:
    # Get OpenAI key from environment variable or user input
    get_openai_key_sidebar()

    # Get username
    username = get_username_sidebar()
    if username:
        st.sidebar.info(f":technologist: User: {username}")
    else:
        st.markdown("---")
        st.markdown(
            "#### :technologist: Enter a username to start. Your profile and chat history will be saved."
        )
        return

    # Get the assistant
    coffee_assistant: Assistant = get_coffee_assistant(
        user_id=username,
        debug_mode=True,
    )

    # Get the run id
    coffee_assistant_run_ids: List[str] = coffee_assistant.storage.get_all_run_ids(
        user_id=username
    )
    coffee_assistant_run_id = None
    if not coffee_assistant_run_ids or len(coffee_assistant_run_ids) == 0:
        coffee_assistant_run_id = coffee_assistant.create_run()
    else:
        coffee_assistant_run_id = coffee_assistant_run_ids[0]
    coffee_assistant.run_id = coffee_assistant_run_id

    # Create assistant run (i.e. log to database) and save run_id in session state
    st.session_state["coffee_assistant_run_id"] = coffee_assistant.create_run()

    # Check if knowlege base exists
    if coffee_assistant.knowledge_base and (
        "pdf_knowledge_base_loaded" not in st.session_state
        or not st.session_state["pdf_knowledge_base_loaded"]
    ):
        if not coffee_assistant.knowledge_base.exists():
            logger.info("Knowledge base does not exist")
            loading_container = st.sidebar.info("🧠 Loading knowledge base")
            coffee_assistant.knowledge_base.load()
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base loaded")
            loading_container.empty()

    # Check if knowlege base exists
    if coffee_assistant.knowledge_base and (
        "pdf_knowledge_base_loaded" not in st.session_state
        or not st.session_state["pdf_knowledge_base_loaded"]
    ):
        if not coffee_assistant.knowledge_base.exists():
            logger.info("Knowledge base does not exist")
            loading_container = st.sidebar.info("🧠 Loading knowledge base")
            coffee_assistant.knowledge_base.load()
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base loaded")
            loading_container.empty()

    # Load messages for existing assistant
    assistant_chat_history = coffee_assistant.memory.get_chat_history()
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
                for delta in coffee_assistant.run(question, stream=False):
                    response += delta  # type: ignore
                    resp_container.markdown(response)

            st.session_state["messages"].append(
                {"role": "assistant", "content": response}
            )

    # if st.sidebar.button("New Run"):
    #     restart_assistant()

    if coffee_assistant.knowledge_base:
        if st.sidebar.button("Update Knowledge Base"):
            coffee_assistant.knowledge_base.load(recreate=False, upsert=True)
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base updated")

        if st.sidebar.button("Recreate Knowledge Base"):
            coffee_assistant.knowledge_base.load(recreate=True)
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base recreated")

        if st.sidebar.button("Clear Knowledge Base"):
            coffee_assistant.knowledge_base.vector_db.clear()
            st.session_state["pdf_knowledge_base_loaded"] = False
            st.sidebar.success("Knowledge base cleared")

    # if st.sidebar.button("Auto Rename"):
    #     coffee_assistant.auto_rename_run()

    # Upload PDF
    if coffee_assistant.knowledge_base:
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
                    coffee_assistant.knowledge_base.load_documents(pdf_documents)
                else:
                    st.sidebar.error("Could not read PDF")
                st.session_state[f"{pdf_name}_uploaded"] = True
            alert.empty()

    # # Run id selector
    # if coffee_assistant.storage:
    #     coffee_assistant_run_ids: List[str] = coffee_assistant.storage.get_all_run_ids(user_id=username)
    #     new_coffee_assistant_run_id = st.sidebar.selectbox("Run ID", options=coffee_assistant_run_ids)
    #     if st.session_state["coffee_assistant_run_id"] != new_coffee_assistant_run_id:
    #         logger.debug(f"Loading run {new_coffee_assistant_run_id}")
    #         if st.session_state["coffee_assistant_type"] == "Autonomous":
    #             logger.info("---*--- Loading as Autonomous Assistant ---*---")
    #             st.session_state["coffee_assistant"] = get_autonomous_coffee_assistant(
    #                 user_id=username,
    #                 run_id=new_coffee_assistant_run_id,
    #                 debug_mode=True,
    #             )
    #         else:
    #             logger.info("---*--- Loading as RAG Assistant ---*---")
    #             st.session_state["coffee_assistant"] = get_rag_coffee_assistant(
    #                 user_id=username,
    #                 run_id=new_coffee_assistant_run_id,
    #                 debug_mode=True,
    #             )
    #         st.rerun()

    # coffee_assistant_run_name = coffee_assistant.run_name
    # if coffee_assistant_run_name:
    #     st.sidebar.write(f":thread: {coffee_assistant_run_name}")

    # # Show reload button
    # reload_button_sidebar()


main()
