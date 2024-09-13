from typing import Callable, List

import streamlit as st
from phi.assistant import Assistant
from phi.document import Document
from phi.document.reader.pdf import PDFReader
from phi.memory.manager import MemoryManager
from PIL import Image

from ai.tools.adapters.mock_cart import (
    calculate_tax_fees_and_total,
    get_adora_list_of_items,
    hard_reset_mock_cart,
    load_mock_cart,
    reset_mock_cart,
)
from app.auth import user
from data_access_layer.dal_user_id import get_user_id_for_account_name_user_email
from utils.log import logger


def demo_ui(
    get_assistant: Callable[[str, bool], Assistant],
) -> None:
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

    # Reset memory
    if st.session_state.get("reset_memory"):
        if assistant.memory.manager is None:
            assistant.memory.manager = MemoryManager(
                user_id=assistant.memory.user_id, db=assistant.memory.db
            )
        assistant.memory.manager.clear_memory()
        st.session_state["reset_memory"] = False

    # Debug UI
    if user.account_name == "proactiveailab" or user.account_name == "root":
        debug_ui(assistant)

    # Load existing or create new run
    assistant.create_run()
    # Messaging UI
    messaging_ui(assistant)
    # Settings UI
    memory_ui(assistant)
    knowledge_base_ui(assistant)
    # storage_ui(assistant)
    if assistant.name == "pizza_assistant":
        cart_ui(user_id)


demo_system_prompt = ""


def cart_ui(user_id):
    """
    This function displays the cart information in the sidebar
    """
    cart = load_mock_cart(user_id)
    cart_dict = cart.model_dump()

    # Display customer information
    st.sidebar.write("***")
    st.sidebar.image("data/pizza/logos/pizza_my_heart_logo.png", use_column_width=True)
    st.sidebar.write("## Customer Information")
    st.sidebar.write(
        f"**📇 Name:** {cart_dict['user']['first_name']} {cart_dict['user']['last_name']}"
    )
    st.sidebar.write(f"**📞 Telephone:** {cart_dict['user']['phone_number']}")
    st.sidebar.write(f"**📨 Email:** {cart_dict['user']['email']}")
    st.sidebar.write("")
    st.sidebar.write("***")
    # Display cart items
    st.sidebar.write("## Items")
    if cart_dict["list_of_cart_items"]:
        st.sidebar.write(
            f"**Total Price:** {calculate_tax_fees_and_total(cart.store_id, get_adora_list_of_items(cart)).Total}"
        )  # TODO: get rid of squiggle here
        for item in cart_dict["list_of_cart_items"]:
            st.sidebar.write(
                "Item: "
                + str(item["quantity"])
                + " "
                + item["size"]
                + " "
                + item["item_name"]
            )
            modification_string = ""
            for mod in item["modifications"]:
                modification_string += mod + ", "
            modification_string = modification_string[:-2]
            st.sidebar.write("Modifications: " + modification_string)
            st.sidebar.write("Adora Item:")
            st.sidebar.json(item["pos_item"])
            st.sidebar.write("")

    # Display store and order type information
    st.sidebar.write("## Order Information")
    st.sidebar.write("**🎫 Store ID:** " + cart_dict["store_id"])
    if not cart_dict["order_type"]:
        st.sidebar.write("**🍕 Order Type:** ")
    else:
        st.sidebar.write(f"**🍕 Order Type:** {cart_dict['order_type'].value}")
    st.sidebar.write("**📍 Delivery Address:**")
    if cart_dict["address_for_delivery"]:
        st.sidebar.json(cart_dict["address_for_delivery"])


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

    def reset_memory():
        st.session_state["reset_memory"] = True
        st.rerun()

    def reset_cart():
        """
        Resets the cart items and order type then reruns
        """
        user_id = get_user_id_for_account_name_user_email(user.account_name, user.email)
        reset_mock_cart(user_id)
        st.rerun()

    def hard_reset_cart():
        """
        Completely removes the user from the cart
        """
        user_id = get_user_id_for_account_name_user_email(user.account_name, user.email)
        hard_reset_mock_cart(user_id)
        st.rerun()

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        if st.button("Restart Chat"):
            restart_chat()
    with col2:
        if st.button("Reset Memory"):
            reset_memory()
    with col3:
        if st.button("Reset Cart"):
            reset_cart()
    with col4:
        if st.button("Hard Reset Cart"):
            hard_reset_cart()


def messaging_ui(assistant: Assistant) -> None:
    assistant_chat_history = assistant.memory.get_chat_history()
    for message in assistant_chat_history:
        message["content"] = message["content"].replace("\$", "💲").replace("$", "💲")
    st.session_state["messages"] = assistant_chat_history
    if assistant_chat_history == []:
        # Set initial message for lazydog assistant
        if assistant.name == "lazydog_assistant":
            st.session_state["messages"] = [
                {"role": "assistant", "content": "I am Doug. I work at Lazy Dog Restaurant. I am here to help you Eat, Drink and have a great time at our Lazy Dog Restaurant"}
            ]
        # else set initial message for general assistant
        else:
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
        # Set Avatar For Adora / Pizza My Heart; Lazy Dog
        if assistant.name == "pizza_assistant":
            avatar = (
                "data/pizza/logos/jimmy_the_surfer.png"
                if message["role"] == "assistant"
                else None
            )
        elif assistant.name == "lazydog_assistant":
            avatar = (
                "data/lazydog/logos/LZRLogo.png"
                if message["role"] == "assistant"
                else None
            )
        else:
            avatar = None
        with st.chat_message(message["role"], avatar=avatar):
            st.write(message["content"])

    # If last message is from a user, generate a new response
    try:
        last_message = st.session_state["messages"][-1]
        if last_message.get("role") == "user":
            assistant.system_prompt = demo_system_prompt
            question = last_message["content"]
            # For Adora / Pizza My Heart
            if assistant.name == "pizza_assistant":
                generate_response_in_ui(
                    assistant,
                    question,
                    avatar_path="data/pizza/logos/jimmy_the_surfer.png",
                )
            elif assistant.name == "lazydog_assistant":
                generate_response_in_ui(
                    assistant,
                    question,
                    avatar_path="data/lazydog/logos/LZRLogo.png",
                )
            else:
                generate_response_in_ui(assistant, question)
    except IndexError:
        pass


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


def generate_response_in_ui(assistant, question, avatar_path=None):
    """
    Generates a response from the assistant and displays it in the chat interface.
    Simplifying the code to insert Jimmy the Surfer and other customizations.

    Parameters:
    assistant (object): The assistant object that will generate the response.
    question (str): The question or prompt to which the assistant will respond.
    avatar_path (str, optional): The file path to the avatar image to be displayed with the assistant's message. Defaults to None.

    Returns:
    None

    Raises:
    Exception: Raises an exception if an error occurs during response generation after 5 attempts.
    """
    with st.chat_message(
        "assistant", avatar=Image.open(avatar_path) if avatar_path else None
    ):
        with st.spinner("Working..."):

            MAX_RETRIES = 5
            retries = 0
            error = ""
            response = ""
            while retries < MAX_RETRIES:
                try:
                    resp_container = st.empty()
                    for delta in assistant.run(question, stream=False):
                        # Sometimes delta will return a non-string type object
                        if isinstance(delta, str):
                            response += delta.replace("\$", "💲").replace("$", "💲")
                            resp_container.markdown(response)
                    break  # Exit the loop if the response is generated
                except Exception as e:
                    error = e
                    logger.error(f"Error generating response: {e}")
                    retries += 1
                    st.warning(
                        f"An error occurred: Retrying... (Attempt {retries}/{MAX_RETRIES})"
                    )

            if retries == MAX_RETRIES:
                st.error(
                    f"Error: {error}\nFailed to generate a response after multiple attempts."
                )

        st.session_state["messages"].append({"role": "assistant", "content": response})
