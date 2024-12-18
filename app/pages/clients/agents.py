import json
import time

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from app.shared import get_app_db, json_decode, universal_picker_ui
from services.account_service import get_account
from services.agent_service import get_agent, replace_agent_config

st.title("Agents")

session = get_app_db()


def _render_agent_config_form(
    cur_config: dict | list, new_config: dict | list, cur_path: str, key
) -> None:
    """
    Displays a form for an item (dict, list, text, num) in the agent configuration.

    Args:
        cur_config (dict|list): original agent configuration
        new_config (dict|list): new config that is being dynamically built
        path (str): path to the item in focus. Used only as an input label
        key (str|int): key/index to the item in focus

    Returns:
        None, modifies new_config in place
    """
    if not isinstance(cur_config[key], list):
        # eliminates some redundant text
        st.text(cur_path)
    if isinstance(cur_config[key], dict):
        new_config[key] = dict(cur_config[key])
        _render_agent_config_form_dict(cur_config[key], new_config[key], cur_path)
    elif isinstance(cur_config[key], list):
        new_config[key] = list(cur_config[key])
        _render_agent_config_form_list(cur_config[key], new_config[key], cur_path)
    elif isinstance(cur_config[key], int) or isinstance(cur_config[key], float):
        new_config[key] = st.number_input(key=cur_path, label="", value=cur_config[key])
        st.divider()
    else:
        # text input
        new_config[key] = st.text_area(key=cur_path, label="", value=cur_config[key])
        st.divider()


def _render_agent_config_form_dict(
    cur_config: dict, new_config: dict, path: str
) -> None:
    """
    Dictionary wrapper for _render_agent_config_form
    """
    keys = cur_config.keys()
    if not keys:
        return
    tabs = st.tabs(list(keys))
    for key, tab in zip(keys, tabs):
        with tab:
            cur_path = f"{path}.{key}" if path else key
            new_config[key] = cur_config[key]
            _render_agent_config_form(cur_config, new_config, cur_path, key)


def _render_agent_config_form_list(
    cur_config: list, new_config: list, path: str
) -> None:
    """
    List wrapper for _render_agent_config_form
    """
    for i, _ in enumerate(cur_config):
        cur_path = f"{path}[{i}]"
        new_config[i] = cur_config[i]
        _render_agent_config_form(cur_config, new_config, cur_path, i)


def main() -> None:
    st.write("---")

    if "account_name" not in st.session_state:
        st.error("Please Select an Account to View")
        return

    account_name = st.session_state["account_name"]
    account = get_account(session, account_name)
    agent = get_agent(session, account.agents[0].id) if account else None

    if agent is None:
        st.write("Agent not found")
    else:
        st.subheader("Agent Update")

        st.write(
            ":orange-background[Please __double-check any modifications__ before submitting.]"
        )
        st.divider()

        unformatted_json = dict(agent.raw_config)
        formatted_json = json.dumps(unformatted_json, indent=4, ensure_ascii=False)
        formatted_json_str = str(formatted_json)
        if f"{agent.id}_starting_config" not in st.session_state:
            st.session_state[f"{agent.id}_starting_config"] = unformatted_json

        st.write(":red[__Revert__] agent config to start of session")
        if st.button("Revert"):
            replace_agent_config(
                session,
                agent_id=agent.id,
                config=st.session_state[f"{agent.id}_starting_config"],
            )
            # flash message, then rerun to reflect changes
            st.success("Successfully reverted the agent config. Rerunning...")
            time.sleep(1)
            st.rerun()
        st.divider()

        st.write(":red[__Replace__] the entire agent config")
        with st.form(key="replace_agent_config_form"):
            replace_config_expander = st.expander("Replace Agent Config")
            replace_config = replace_config_expander.text_area(
                "Replace Agent Config",
                value=formatted_json_str,
                height=400,
                label_visibility="collapsed",
            )

            # Submit button
            if st.form_submit_button(label="Submit"):
                replace_config_json = json_decode(replace_config)
                if replace_config_json:
                    replace_agent_config(
                        session,
                        agent_id=agent.id,
                        config=replace_config_json,
                    )
                    st.success("Successfully replaced the agent config. Rerunning...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid JSON format")
        st.divider()

        st.write(":red[__Edit__] agent config values")
        with st.expander("Edit Agent Config"):
            st.write(
                """
                Notes:
                - Use tabs to navigate across the config keys
                - This can edit values, but not the overall structure. These cannot change:
                    - Keys
                    - Values types
                    - Lists lengths
                - Float input saves all digits, despite only showing 2 decimal places
                - Scrolling on a number input can subtly increment/decrement the value
                """
            )
            with st.form(key="update_agent_config_form", border=False):
                new_config = {}
                _render_agent_config_form_dict(unformatted_json, new_config, "")
                submitted = st.form_submit_button("Submit")
                if submitted:
                    replace_agent_config(
                        session,
                        agent_id=agent.id,
                        config=new_config,
                    )
                    st.success("Successfully updated the agent config. Rerunning...")
                    time.sleep(1)
                    st.rerun()
        st.divider()

        st.subheader("Agent Config")
        st.json(agent.raw_config)

        st.subheader("Agent Database Information")
        st.write(agent)


if user.is_logged_in:
    universal_picker_ui(session)
    main()
else:
    switch_page("home")
