# from typing import List

import streamlit as st
from phi.assistant import Assistant

# from phi.document import Document
# from phi.document.reader.pdf import PDFReader
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.pizza_assistant import get_pizza_assistant
from app.auth import user, user_ui
from utils.log import logger

st.set_page_config(
    page_title="Pizza",
    page_icon="🍕",
)
st.title("Pizza")


def main() -> None:
    # Get the assistant
    assistant: Assistant = get_pizza_assistant(
        user_id=user.username,
        debug_mode=False,
    )

    assistant.storage = None

    # # Get the run id
    # assistant_run_ids: List[str] = assistant.storage.get_all_run_ids(
    #     user_id=user.username
    # )
    # assistant_run_id = None
    # if not assistant_run_ids or len(assistant_run_ids) == 0:
    #     assistant_run_id = assistant.create_run()
    # else:
    #     assistant_run_id = assistant_run_ids[0]
    # assistant.run_id = assistant_run_id

    # Create assistant run (i.e. log to database) and save run_id in session state
    st.session_state["pizza_assistant_run_id"] = assistant.create_run()

    # Check if knowledge base exists
    if assistant.knowledge_base and (
        "pdf_knowledge_base_loaded" not in st.session_state
        or not st.session_state["pdf_knowledge_base_loaded"]
    ):
        if not assistant.knowledge_base.exists():
            logger.info("Knowledge base does not exist")
            loading_container = st.sidebar.info("🧠 Loading knowledge base")
            assistant.knowledge_base.load()
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base loaded")
            loading_container.empty()

    # Check if knowledge base exists
    if assistant.knowledge_base and (
        "pdf_knowledge_base_loaded" not in st.session_state
        or not st.session_state["pdf_knowledge_base_loaded"]
    ):
        if not assistant.knowledge_base.exists():
            logger.info("Knowledge base does not exist")
            loading_container = st.sidebar.info("🧠 Loading knowledge base")
            assistant.knowledge_base.load()
            st.session_state["pdf_knowledge_base_loaded"] = True
            st.sidebar.success("Knowledge base loaded")
            loading_container.empty()

    show_system_prompt = st.toggle("Show System Prompt", True)
    if show_system_prompt:
        system_prompt = st.text_area(
            "System Prompt",
            assistant.system_prompt,
            height=300,
            label_visibility="collapsed",
        )

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
        assistant.system_prompt = system_prompt
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

    # if st.sidebar.button("New Run"):
    #     restart_assistant()

    # if assistant.knowledge_base:
    #     if st.sidebar.button("Update Knowledge Base"):
    #         assistant.knowledge_base.load(recreate=False, upsert=True)
    #         st.session_state["pdf_knowledge_base_loaded"] = True
    #         st.sidebar.success("Knowledge base updated")

    #     if st.sidebar.button("Recreate Knowledge Base"):
    #         assistant.knowledge_base.load(recreate=True)
    #         st.session_state["pdf_knowledge_base_loaded"] = True
    #         st.sidebar.success("Knowledge base recreated")

    #     if st.sidebar.button("Clear Knowledge Base"):
    #         assistant.knowledge_base.vector_db.clear()
    #         st.session_state["pdf_knowledge_base_loaded"] = False
    #         st.sidebar.success("Knowledge base cleared")

    # if st.sidebar.button("Auto Rename"):
    #     coffee_assistant.auto_rename_run()

    # # Upload PDF
    # if assistant.knowledge_base:
    #     if "file_uploader_key" not in st.session_state:
    #         st.session_state["file_uploader_key"] = 0

    #     uploaded_file = st.sidebar.file_uploader(
    #         "Upload PDF",
    #         type="pdf",
    #         key=st.session_state["file_uploader_key"],
    #     )
    #     if uploaded_file is not None:
    #         alert = st.sidebar.info("Processing PDF...", icon="ℹ️")
    #         pdf_name = uploaded_file.name.split(".")[0]
    #         if f"{pdf_name}_uploaded" not in st.session_state:
    #             reader = PDFReader()
    #             pdf_documents: List[Document] = reader.read(uploaded_file)
    #             if pdf_documents:
    #                 assistant.knowledge_base.load_documents(pdf_documents)
    #             else:
    #                 st.sidebar.error("Could not read PDF")
    #             st.session_state[f"{pdf_name}_uploaded"] = True
    #         alert.empty()

    # coffee_assistant_run_name = coffee_assistant.run_name
    # if coffee_assistant_run_name:
    #     st.sidebar.write(f":thread: {coffee_assistant_run_name}")

    # # Show reload button
    # reload_button_sidebar()


if user.is_logged_in:
    main()
    user_ui()
else:
    switch_page("home")
