import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.coffee_assistant import get_coffee_assistant
from app.auth import user
from app.demo_template import demo_ui
from app.shared import set_page_config

set_page_config()

st.title("Coffee Assistant")


if user.is_logged_in:
    demo_ui(get_coffee_assistant)
else:
    switch_page("home")
