import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.gym_assistant import get_gym_assistant
from app.auth import user
from app.demo_template import main_ui

st.title("Gym Assistant")


if user.is_logged_in:
    main_ui(get_gym_assistant)
else:
    switch_page("home")
