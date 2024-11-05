import json
import time
import uuid

import streamlit as st
from phi.agent.agent import Agent
from phi.memory.manager import MemoryManager
from phi.memory.memory import Memory
from phi.run.response import RunResponse
from PIL import Image

from api.schemas.message.message import Channel
from app.auth import user
from db.session import get_db
from services.account_service import get_account
from services.assistant_service import get_ai_agent, get_assistant
from services.user_service import get_user_by_channel_identifier
from utils.log import logger


def get_prd_agent(
    user_id: str,
    agent_id: uuid.UUID,
    new_run: bool = False,
) -> Agent:
    db = next(get_db())
    prd_assistant = get_assistant(db, agent_id)

    account = None
    if prd_assistant is not None:
        account = get_account(db, account_name=prd_assistant.account.name)

    if account is None:
        raise ValueError("Account not found")

    if not account.projects:
        raise ValueError("No projects found for this account")

    db_user = get_user_by_channel_identifier(
        db,
        account_id=account.id,
        channel_identifier=f"{Channel.INTERNAL_APP.value}:{user_id}",
        create_new_user=True,
    )

    if not db_user:
        raise ValueError("User not found in db")

    ai_agent: Agent = get_ai_agent(
        db,
        assistant_id=agent_id,
        user_id=db_user.id,
        new_run=new_run,
    )
    return ai_agent


def demo_ui(
    agent_id: uuid.UUID,
) -> None:
    if not user.email:
        st.error(
            "Current is missing an email. Please ensure you are logged in with a valid email address."
        )
        st.stop()
    if st.session_state.get("restart_chat"):
        logger.info("Restarting chat")
        agent = get_prd_agent(
            user_id=user.email,
            agent_id=agent_id,
            new_run=True,
        )
        agent.memory.messages = []
        st.session_state["messages"] = []
    else:
        logger.info("Not restarting chat")
        agent = get_prd_agent(
            user_id=user.email,
            agent_id=agent_id,
            new_run=False,
        )
    st.session_state["restart_chat"] = False

    # Reset memory
    if st.session_state.get("reset_memory"):
        if agent.memory.manager is None:
            agent.memory.manager = MemoryManager(
                user_id=agent.memory.user_id, db=agent.memory.db
            )
        agent.memory.manager.clear_memory()
        st.session_state["reset_memory"] = False

    # Debug UI
    debug_ui(agent)

    # Load existing or create new run
    agent.load_session()
    # Messaging UI
    messaging_ui(agent)
    # Settings UI
    memory_ui(agent)
    # storage_ui(assistant)


demo_system_prompt = ""


def debug_ui(agent: Agent):
    # System Prompt
    system_prompt_expander = st.expander("System Prompt")
    global demo_system_prompt
    demo_system_prompt = system_prompt_expander.text_area(
        "System Prompt",
        agent.system_prompt,
        height=300,
        label_visibility="collapsed",
    )
    # Debug Info
    with st.expander("Debug Info"):
        st.info(f"Agent Name: {agent.name}")
        st.info(f"Session ID: {agent.session_id}")
        agent.show_tool_calls = st.toggle("Show Tool Calls", agent.show_tool_calls)

    # Restart chat
    def restart_chat():
        st.session_state["restart_chat"] = True
        st.rerun()

    def reset_memory():
        st.session_state["reset_memory"] = True
        st.rerun()

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        if st.button("Restart Chat"):
            restart_chat()
    with col2:
        if st.button("Reset Memory"):
            reset_memory()


def messaging_ui(agent: Agent) -> None:
    agent_chat_history = agent.memory.get_messages()
    st.session_state["messages"] = agent_chat_history
    # Prompt for user input
    if prompt := st.chat_input():
        st.session_state["messages"].append({"role": "user", "content": prompt})
    # Display existing chat messages
    for message in st.session_state["messages"]:
        if message["role"] == "system":
            continue

        else:
            with st.chat_message(message["role"]):
                if "content" not in message:
                    continue  # skip empty messages
                if message["role"] == "agent":
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
            agent.system_prompt = demo_system_prompt
            question = last_message["content"]
            generate_response_in_ui(agent, question)
    except IndexError:
        pass


def memory_ui(agent: Agent) -> None:
    st.sidebar.write("## Memory")
    # Display existing memories
    if agent.memory.memories:
        for item in agent.memory.memories:
            col1, col2 = st.sidebar.columns([12, 2.5])
            with col1:
                st.warning(item.memory)
            with col2:
                st.write("")
                if st.button("✕", key=f"remove_memory_{item}"):
                    clear_memory(agent, item)
                    st.rerun()
    # Add the "Add Memory" button
    if "add_memory" not in st.session_state:
        st.session_state["add_memory"] = False
    if st.sidebar.button("Add Memory"):
        st.session_state["add_memory"] = not st.session_state["add_memory"]

    # Show the text input field when "Add Memory" is clicked
    if st.session_state["add_memory"]:
        memory_text = st.sidebar.text_input("Enter memory")
        if st.sidebar.button("Save"):
            if memory_text:
                new_memory = Memory(input=memory_text, memory=memory_text)
                add_memory(agent, new_memory)
                # Close the text field after saving
                st.session_state["add_memory"] = False
                st.rerun()
    st.sidebar.markdown("---")


def add_memory(agent: Agent, memory: Memory) -> None:
    """
    Adds the specified memory to both the agent's memory list and the memory database.

    Parameters:
    agent (Agent): The `Agent` instance that will generate the response.
    memory (Memory): The `Memory` instance to be added.

    Returns:
    None

    """
    if agent.memory.manager is None:
        agent.memory.manager = MemoryManager(
            user_id=agent.memory.user_id, db=agent.memory.db
        )

    agent.memory.manager.add_memory(memory.memory)


def clear_memory(agent: Agent, removed_memory: Memory) -> None:
    """
    Clears the specified memory from both the agent's memory list and the memory database.

    Parameters:
    agent (Agent): The `Agent` instance that will generate the response.
    removed_memory (Memory): The `Memory` object to be removed.

    Returns:
    None

    """

    if agent.memory.manager is None:
        agent.memory.manager = MemoryManager(
            user_id=agent.memory.user_id, db=agent.memory.db
        )

    memories = agent.memory.memories
    if memories and removed_memory and removed_memory in memories:
        memories.remove(removed_memory)
    agent.memory.manager.clear_memory()
    if memories:
        for memory in memories:
            agent.memory.manager.add_memory(memory.memory)


# def storage_ui(assistant: Agent) -> None:
#     st.sidebar.write("## Storage")
#     assistant.auto_rename_run()
#     st.sidebar.success(assistant.run_name)
#     if assistant.storage:
#         st.sidebar.success(
#             f"Number of chats: {len(assistant.memory.get_chat_history())}"
#         )


def generate_response_in_ui(agent: Agent, question, avatar_path=None):
    """
    Generates a response from the agent and displays it in the chat interface.

    Parameters:
    agent (object): The agent object that will generate the response.
    question (str): The question or prompt to which the agent will respond.
    avatar_path (str, optional): The file path to the avatar image to be displayed with the agent's message. Defaults to None.

    Returns:
    None

    Raises:
    Exception: Raises an exception if an error occurs during response generation after 5 attempts.
    """

    def display_elapsed_time(container, start_time):
        container.text(f"Response generated in {time.time() - start_time:.2f} seconds")

    with st.chat_message(
        "agent", avatar=Image.open(avatar_path) if avatar_path else None
    ):
        with st.spinner("Working..."):
            MAX_RETRIES = 5
            retries = 0
            error = ""
            response = ""
            while retries < MAX_RETRIES:
                start_time = time.time()
                elapsed_container = st.empty()
                try:
                    resp_container = st.empty()
                    response_object: RunResponse = agent.run(question, stream=False)
                    if isinstance(response_object, str):
                        # TODO this case never happens
                        raise Exception("FATAL ERROR")
                    else:
                        response = response_object.content
                        if not response:
                            # TODO do something here
                            return
                        response_content = response.content
                        response_content = response_content.replace(
                            r"\$", "💲"
                        ).replace("$", "💲")
                        resp_container.markdown(response_content)
                        extras = {"escalated": response.escalated}
                        st.json(extras)
                        display_elapsed_time(elapsed_container, start_time)

                    break  # Exit the loop if the response is generated
                except Exception as e:
                    error = e
                    logger.error(f"Error generating response: {e}")
                    retries += 1
                    st.warning(
                        f"An error occurred: Retrying... (Attempt {retries}/{MAX_RETRIES})"
                    )
                    display_elapsed_time(elapsed_container, start_time)

            if retries == MAX_RETRIES:
                st.error(
                    f"Error: {error}\nFailed to generate a response after multiple attempts."
                )

        st.session_state["messages"].append({"role": "agent", "content": response})
