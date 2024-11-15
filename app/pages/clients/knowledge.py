import json
import uuid
from typing import Any, List

import streamlit as st
from phi.document.base import Document
from phi.document.reader.pdf import PDFReader
from sqlalchemy import DateTime, MetaData, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.orm.session import Session
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from streamlit_extras.switch_page_button import switch_page

from ai.knowledge import get_knowledge
from app.auth import user
from app.shared import account_picker_ui
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

        dashboards, tab_pdf, tab_text, tab_json = st.tabs(
            ["Dashboards", "PDF Uploader", "Text Uploader", "JSON Uploader"]
        )
        with dashboards:
            if knowledge_base:
                knowledge_dashboard_ui(account_name)

        with tab_pdf:
            # Upload PDF
            if knowledge_base:
                with st.form("my-form-pdf", clear_on_submit=True):
                    uploaded_file = st.file_uploader(
                        "Upload PDF Here:",
                        type="pdf",
                    )
                    submitted = st.form_submit_button("UPLOAD")

                if uploaded_file and submitted:
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
                with st.form("my-form-text", clear_on_submit=True):
                    uploaded_files = st.file_uploader(
                        "Text Uploader",
                        type="txt",
                        accept_multiple_files=True,
                    )
                    submitted = st.form_submit_button("UPLOAD")

                if uploaded_files and submitted:
                    alert = st.info("Processing Text...", icon="ℹ️")
                    text_documents: List[Document] = []

                    for uploaded_file in uploaded_files:
                        text_name = uploaded_file.name.split(".")[0]
                        # Read file content, decode and load as JSON
                        file_content = uploaded_file.read().decode("utf-8")
                        json_document = Document(content=file_content, name=text_name)
                        text_documents.append(json_document)
                    if text_documents:
                        oversized_files = []
                        for doc in text_documents:
                            try:
                                knowledge_base.load_document(doc)
                            except Exception:
                                oversized_files.append(doc.name)
                        if oversized_files:
                            st.warning(
                                "Error: The following documents are oversize and have been skipped:\n\n"
                                + ", ".join(
                                    [
                                        f"**{file_name}**"
                                        for file_name in oversized_files
                                    ]
                                )
                                + "\n\nPlease shorten or contact support."
                            )
                        else:
                            st.success(
                                "Text files processed and loaded into the knowledge base"
                            )
                        alert.empty()
                    else:
                        st.error("No valid Text files to load")
                    st.session_state["text_uploaded"] = True

                st.write("---")
                st.info("Manually upload Text below:")
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
                if "file_uploader_key" not in st.session_state:
                    st.session_state["file_uploader_key"] = 0

                with st.form("my-form", clear_on_submit=True):
                    uploaded_files = st.file_uploader(
                        "JSON Uploader",
                        type="json",
                        accept_multiple_files=True,
                        key=st.session_state["file_uploader_key"],
                    )
                    submitted = st.form_submit_button("UPLOAD")

                if uploaded_files and submitted:
                    alert = st.info("Processing JSON...", icon="ℹ️")
                    json_documents: List[Document] = []

                    for uploaded_file in uploaded_files:
                        json_name = uploaded_file.name.split(".")[0]

                        try:
                            # Read file content, decode and load as JSON
                            file_content = uploaded_file.read().decode("utf-8")
                            json_file = json.loads(file_content)

                            # Compress JSON and create Document object
                            compressed_json = json.dumps(
                                json_file, separators=(",", ":")
                            )
                            json_document = Document(
                                content=compressed_json, name=json_name
                            )
                            json_documents.append(json_document)

                        except json.JSONDecodeError:
                            st.error(f"Failed to parse JSON file: {uploaded_file.name}")

                    if json_documents:
                        oversized_files = []
                        for doc in json_documents:
                            try:
                                knowledge_base.load_document(doc)
                            except Exception:
                                oversized_files.append(doc.name)
                        if oversized_files:
                            st.warning(
                                "Error: The following documents are oversize and have been skipped:\n\n"
                                + ", ".join(
                                    [
                                        f"**{file_name}**"
                                        for file_name in oversized_files
                                    ]
                                )
                                + "\n\nPlease shorten or contact support."
                            )
                        else:
                            st.success(
                                "JSON files processed and loaded into the knowledge base"
                            )

                    else:
                        st.error("No valid JSON files to load")
                    alert.empty()
                    st.session_state["json_uploaded"] = True

                st.write("---")
                st.info("Manually upload JSON below:")
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
                                "Sorry, the JSON you provided is **too large** \n. Please provide a shorter JSON or contact support."
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
                        knowledge_base.delete()
                        st.session_state["knowledge_base_loaded"] = False
                        st.success("Knowledge base cleared")
                    else:
                        st.warning("Operation cancelled")
                    del st.session_state.confirmation_result

    else:
        st.error("Please Select an Account to Edit Knowledge Base")


def knowledge_dashboard_ui(account_name: str) -> None:
    knowledge_base_ai = get_knowledge_by_account_name(db, account_name)
    # Define page size and initialize session state for pagination
    if knowledge_base_ai:
        PAGE_SIZE = 10  # Number of items per page
        page_key = f"{account_name}_page_number"
        st.session_state.setdefault(page_key, 0)

        # Convert the list of objects to a list of dictionaries for easier table display
        knowledge_data = [
            {
                "name": item.name,
                "content": item.content,
                "id": item.id,
            }  # Assuming `id` uniquely identifies each entry
            for item in knowledge_base_ai
        ]
        if knowledge_data:
            # Function to get the current page of data
            def get_page_data(data, page_number, page_size):
                start = page_number * page_size
                end = start + page_size
                return data[start:end]

            # Calculate total number of pages
            total_pages = max((len(knowledge_data) - 1) // PAGE_SIZE + 1, 1)

            # Get data for the current page
            current_page_data = get_page_data(
                knowledge_data,
                st.session_state[page_key],
                PAGE_SIZE,
            )

            # Display header
            st.write(f"### {account_name}'s Knowledge Base")

            def is_json(item):
                try:
                    json.loads(item)
                    return True
                except ValueError:
                    return False

            # Display each entry in an expandable "card" format
            for entry in current_page_data:
                with st.expander(f"**{entry['name']}**", expanded=False):
                    col1, col2 = st.columns([10, 1])  # Adjust ratios as needed
                    with col2:
                        if st.button("x", key=f"delete_{entry['id']}"):
                            delete_knowledge_by_id(db, account_name, entry["id"])
                            st.rerun()
                    if is_json(entry["content"]):
                        st.json(entry["content"])
                    else:
                        st.text(entry["content"])

            # Pagination Controls
            col1, _, col2, _, col3 = st.columns([1, 1, 1, 1, 1])

            with col1:
                # Disable the Previous button if on the first page
                if st.session_state[page_key] > 0:
                    if st.button("Previous"):
                        st.session_state[page_key] -= 1
                        st.rerun()
            # Display page information in the center column
            with col2:
                st.write(f"Page {st.session_state[page_key] + 1} of {total_pages}")

            with col3:
                # Disable the Next button if on the last page
                if st.session_state[page_key] < total_pages - 1:
                    if st.button("Next"):
                        st.session_state[page_key] += 1
                        st.rerun()


class AIBase(DeclarativeBase):
    """
    Base class for SQLAlchemy model definitions in the AI schema.
    """

    metadata = MetaData(schema="ai")


class KnowledgeBase(AIBase):
    __abstract__ = True

    id = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
        index=True,
    )
    name = mapped_column(String, nullable=False)
    meta_data = mapped_column(JSONB, nullable=True)
    content = mapped_column(Text, nullable=False)
    embedding = mapped_column(Text, nullable=True)
    usage = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    content_hash = mapped_column(String, nullable=False, unique=True)


# Cache for dynamically created Knowledge classes with unique table names
knowledge_table_cache = {}


def get_knowledge_table(account_name: str):
    if account_name in knowledge_table_cache:
        return knowledge_table_cache[account_name]

    # Dynamically create a Knowledge class with a specific table name
    knowledge_table = type(
        f"{account_name}_Knowledge",
        (KnowledgeBase,),
        {
            "__tablename__": f"{account_name}_knowledge",
            "__table_args__": {"extend_existing": True},
        },
    )
    knowledge_table_cache[account_name] = knowledge_table
    return knowledge_table


def get_knowledge_by_account_name(db: Session, account_name: str) -> List[Any]:
    """
    Retrieve the AI knowledge for a given account name.

    Args:
        account_name (str): The account name to retrieve the AI knowledge for.
    Returns:
        List[Any]: A list of AI knowledge.
    """
    # Get the dynamically generated Knowledge class with the appropriate table name
    knowledge_table = get_knowledge_table(account_name)
    return db.query(knowledge_table).all()


def delete_knowledge_by_id(db: Session, account_name: str, knowledge_id: str) -> None:
    """
    Delete AI knowledge by the knowledge ID.

    Args:
        account_name (str): The account name to retrieve the AI knowledge for
        knowledge_id (str): The ID of the knowledge to delete.
    Returns:
        KnowledgeBase | None: The deleted AI knowledge or None if no such knowledge is found.
    """
    knowledge_class = get_knowledge_table(account_name)
    deleted_knowledge = (
        db.query(knowledge_class).filter(knowledge_class.id == knowledge_id).first()
    )
    try:
        if deleted_knowledge:
            db.delete(deleted_knowledge)
            db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error deleting account: {e}")
    return None


def main() -> None:
    st.write("---")
    account_name = ""
    if "account_name" in st.session_state:
        account_name = st.session_state["account_name"]
    knowledge_ui(account_name)


if user.is_logged_in:
    main()
    account_picker_ui(db)


else:
    switch_page("home")
