import json
import uuid

import streamlit as st
from phi.assistant import Assistant
from phi.memory.manager import MemoryManager
from PIL import Image

from ai.assistants.pizza_assistant import get_pizza_assistant
from ai.tools.pizza_demo_ordering_tools.adapters.mock_cart import (
    hard_reset_mock_cart,
    load_mock_cart,
    reset_mock_cart,
)
from app.auth import user
from db.session import get_db
from services.account_service import get_account
from services.assistant_service import get_ai_assistant, get_assistant
from services.user_service import get_user_by_channel
from utils.log import logger


def get_prd_assistant(
    user_id: str,
    assistant_id: uuid.UUID,
    new_run: bool = False,
) -> Assistant:
    db = next(get_db())
    assistant = get_assistant(db, assistant_id)

    account = get_account(db, account_name=assistant.account.name)

    if account is None:
        raise ValueError("Account not found")

    if not account.projects:
        raise ValueError("No projects found for this account")

    db_user = get_user_by_channel(
        db,
        account_id=account.id,
        channel_platform="INTERNAL_APP",
        channel_identifier=user_id,
        create_new_user=True,
    )

    if not db_user:
        raise ValueError("User not found in db")

    assistant: Assistant = get_ai_assistant(
        db,
        assistant_id=assistant_id,
        user_id=db_user.id,
        new_run=new_run,
    )
    return assistant


def demo_ui(
    assistant_id: uuid.UUID,
) -> None:
    if st.session_state.get("restart_chat"):
        logger.info("Restarting chat")
        assistant = (
            get_prd_assistant(
                user_id=user.email,
                assistant_id=assistant_id,
                new_run=True,
            )
            if assistant_id != "jimmy_demo"
            else get_pizza_assistant(user.email, new_run=True)
        )
        assistant.memory.chat_history = []
        assistant.memory.llm_messages = []
        st.session_state["messages"] = []
    else:
        logger.info("Not restarting chat")
        assistant = (
            get_prd_assistant(
                user_id=user.email,
                assistant_id=assistant_id,
                new_run=False,
            )
            if assistant_id != "jimmy_demo"
            else get_pizza_assistant(user.email, new_run=False)
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
    debug_ui(assistant)

    # Load existing or create new run
    assistant.create_run()
    # Messaging UI
    messaging_ui(assistant)
    # Settings UI
    memory_ui(assistant)
    # storage_ui(assistant)
    if assistant.name == "pizza_assistant":
        cart_ui(user.email)


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
        reset_mock_cart(user.email)
        st.rerun()

    def hard_reset_cart():
        """
        Completely removes the user from the cart
        """
        hard_reset_mock_cart(user.email)
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
    st.session_state["messages"] = assistant_chat_history
    if assistant_chat_history == []:
        if assistant.name == "pizza_assistant":
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
        # For Adora / Pizza My Heart
        if assistant.name == "pizza_assistant":
            avatar = (
                "data/pizza/logos/jimmy_the_surfer.png"
                if message["role"] == "assistant"
                else None
            )
            with st.chat_message(message["role"], avatar=avatar):
                if message["role"] == "assistant":
                    try:
                        response_object = json.loads(message["content"])
                        response = response_object["content"]
                        extras = {"escalated": response_object["escalated"]}
                        st.write(response)
                        st.json(extras)
                    except Exception:
                        response = message["content"]
                        try:
                            ## handle str format when tool call toggle is on
                            json_start = response.find('''{ "content"''')
                            if json_start == -1:
                                json_start = response.find('''{"content"''')
                            response_object = json.loads(response[json_start:])
                            response = (
                                response[:json_start] + response_object["content"]
                            )
                            extras = {"escalated": response_object["escalated"]}
                            st.write(response)
                            st.json(extras)
                        except Exception:
                            # response = response.replace("\$", "💲").replace("$", "💲")
                            st.write(response)
                else:
                    st.write(message["content"])

        else:
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    try:
                        response_object = json.loads(message["content"])
                        response = response_object["content"]
                        extras = {"escalated": response_object["escalated"]}
                        st.write(response)
                        st.json(extras)
                    except Exception:
                        ## handle the case when show tool call toggle is on
                        response = message["content"]
                        try:
                            ## handle str format when tool call toggle is on
                            json_start = response.find('''{ "content"''')
                            if json_start == -1:
                                json_start = response.find('''{"content"''')
                            response_object = json.loads(response[json_start:])
                            response = (
                                response[:json_start] + response_object["content"]
                            )
                            extras = {"escalated": response_object["escalated"]}
                            st.write(response)
                            st.json(extras)
                        except Exception:
                            # response = response.replace("\$", "💲").replace("$", "💲")
                            st.write(response)
                else:
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
            else:
                generate_response_in_ui(assistant, question)
    except IndexError:
        pass


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
                    response_object = assistant.run(question, stream=False)
                    if isinstance(response_object, str):
                        response = response_object
                        try:
                            ## handle str format when tool call toggle is on
                            json_start = response.find('''{ "content"''')
                            if json_start == -1:
                                json_start = response.find('''{"content"''')
                            response_object = json.loads(response[json_start:])
                            response = (
                                response[:json_start] + response_object["content"]
                            )
                            extras = {"escalated": response_object["escalated"]}
                            resp_container.markdown(response)
                            st.json(extras)
                        except Exception:
                            # response = response.replace("\$", "💲").replace("$", "💲")
                            resp_container.markdown(response)
                    else:
                        response = response_object.content
                        # response = response.replace("\$", "💲").replace("$", "💲")
                        resp_container.markdown(response)
                        extras = {"escalated": response_object.escalated}
                        st.json(extras)

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
