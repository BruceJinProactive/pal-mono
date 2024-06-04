import streamlit as st
from phi.assistant import Assistant
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.coffee_assistant import get_coffee_assistant
from app.auth import user
from app.demo_template import main_ui

assistant: Assistant = get_coffee_assistant(
    user_id=user.username,
)

st.set_page_config(
    page_title=assistant.name,
)
st.title(assistant.name)


if user.is_logged_in:
    main_ui(assistant=assistant)
else:
    switch_page("home")
