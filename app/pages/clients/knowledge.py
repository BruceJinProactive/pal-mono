import json
from typing import List

import streamlit as st
from phi.document.base import Document
from phi.document.reader.pdf import PDFReader
from streamlit_extras.switch_page_button import switch_page

from ai.knowledge import get_knowledge
from app.auth import user
from app.pages.clients.accounts import account_picker_ui
from db.session import get_db
from utils.log import logger

st.title("Knowledge")
db = next(get_db())
account_name = ""


@st.dialog("Confirmation")
def show_confirmation():
    # Use a sidebar or another part of the screen for "popup" effect
    st.write("#### Are you sure you want to clear the knowledge base?")
    col1, col2 = st.columns(2)
    if col1.button("Yes"):
        st.session_state.confirmation_result = True
        st.rerun()
    if col2.button("No"):
        st.session_state.confirmation_result = False
        st.rerun()


def knowledge_ui(account_name: str) -> None:
    if account_name:
        st.warning("[WARNING] Operations on this page are irreversible.")
        # Load knowledge base if not already loaded
        knowledge_base = get_knowledge(account_name)
        if knowledge_base and (
            "knowledge_base_loaded" not in st.session_state
            or not st.session_state["knowledge_base_loaded"]
        ):
            if not knowledge_base.exists():
                logger.info("Knowledge base does not exist")
                loading_container = st.info("🧠 Loading knowledge base")
                knowledge_base.load()
                st.session_state["knowledge_base_loaded"] = True
                st.success("Knowledge base loaded")
                loading_container.empty()

        tab_pdf, tab_text, tab_json = st.tabs(
            ["PDF Uploader", "Text Uploader", "JSON Uploader"]
        )
        with tab_pdf:
            # Upload PDF
            if knowledge_base:
                if "file_uploader_key" not in st.session_state:
                    st.session_state["file_uploader_key"] = 0
                uploaded_file = st.file_uploader(
                    "Upload PDF Here:",
                    type="pdf",
                    key=st.session_state["file_uploader_key"],
                )
                if uploaded_file is not None:
                    alert = st.info("Processing PDF...", icon="ℹ️")
                    pdf_name = uploaded_file.name.split(".")[0]
                    if f"{pdf_name}_uploaded" not in st.session_state:
                        reader = PDFReader()
                        pdf_documents: List[Document] = reader.read(uploaded_file)
                        if pdf_documents:
                            knowledge_base.load_documents(pdf_documents)
                            st.success(
                                "PDF files processed and loaded into knowledge base"
                            )
                        else:
                            st.error("Could not read PDF")
                        st.session_state[f"{pdf_name}_uploaded"] = True
                    alert.empty()
        with tab_text:
            if knowledge_base:
                name_input = st.text_input(
                    "Document Name:", key="text_document_name_key"
                )
                text_input = st.text_area(
                    "Paste or type your Text here:", height=300, key="text_input_key"
                )
                if st.button("Upload Text"):
                    alert = st.info("Processing Submitted Text...", icon="ℹ️")
                    if text_input and name_input:
                        try:
                            text_document = Document(
                                content=text_input, name=name_input
                            )
                            knowledge_base.load_document(text_document)
                            st.success("Text processed and loaded into knowledge base")
                        except Exception:
                            st.error(
                                "Sorry, the text you provided it is **too long** \n, please provide a shorter text or contact support."
                            )
                    if not text_input:
                        st.error("Please paste some Text to process.")
                    if not name_input:
                        st.error("Please provide a document name.")
                    alert.empty()
        with tab_json:
            if knowledge_base:
                json_name_input = st.text_input(
                    "Document Name:", key="json_document_name_key"
                )
                json_input = st.text_area(
                    "Paste or type your JSON here:", height=300, key="json_input_area"
                )
                if st.button("Upload JSON"):
                    if json_input and json_name_input:
                        try:
                            # Attempt to parse the input JSON
                            json_content = json.loads(json_input)

                            # Convert the dictionary back to a JSON string with specific separators
                            compressed_json = json.dumps(
                                json_content, separators=(",", ":")
                            )
                            # Pass the JSON string to the knowledge base for loading
                            knowledge_base.load_document(
                                Document(content=compressed_json, name=json_name_input)
                            )

                            st.success("JSON processed and loaded into knowledge base.")

                        except json.JSONDecodeError as e:
                            st.error(f"Invalid JSON format: {e}")

                        except Exception:
                            st.error(
                                "Sorry, the JSON you provided is **too long** \n. Please provide a shorter JSON or contact support."
                            )

                    if not json_input:
                        st.error("Please paste some JSON to process.")

                    if not json_name_input:
                        st.error("Please provide a document name.")
        if knowledge_base:
            st.text("")
            if st.button("Clear Knowledge Base"):
                show_confirmation()
            if "confirmation_result" in st.session_state:
                if st.session_state.confirmation_result is not None:
                    if st.session_state.confirmation_result:
                        knowledge_base.clear()
                        st.session_state["knowledge_base_loaded"] = False
                        st.success("Knowledge base cleared")
                    else:
                        st.warning("Operation cancelled")
                    del st.session_state.confirmation_result

    else:
        st.error("Please Select an Account to Edit Knowledge Base")


def main() -> None:
    st.write("---")
    account_name = ""
    if "account_name" in st.session_state:
        account_name = st.session_state["account_name"]
    knowledge_ui(account_name)


if user.is_logged_in:
    main()
    account_picker_ui()


else:
    switch_page("home")
