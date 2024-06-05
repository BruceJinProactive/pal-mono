# from typing import List

import streamlit as st

# from phi.document import Document
# from phi.document.reader.pdf import PDFReader
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.pizza_assistant import get_pizza_assistant
from app.auth import user
from app.demo_template import demo_ui
from app.shared import set_page_config

set_page_config()

st.title("Pizz Assistant")


if user.is_logged_in:
    demo_ui(get_pizza_assistant)
else:
    switch_page("home")
