
import streamlit as st
from Auth import (
    AWS_APP_CLIENT_ID,
    AWS_APP_CLIENT_SECRET,
    AWS_USER_POOL_ID,
    user,
)
from st_pages import Page, show_pages
from streamlit_cognito_auth import CognitoAuthenticator

st.set_page_config(
    page_title="Proactive AI Console",
    page_icon=":control-knobs:",
)


st.title("Welcome to Proactive AI!")

st.markdown("---")

# # Sidebar Footer
# footer = """
#     <style>
#     .sidebar .sidebar-content {
#         display: flex;
#         flex-direction: column;
#         justify-content: space-between;
#         height: 100%;
#     }
#     .footer {
#         text-align: center;
#         padding: 10px 0;
#         font-size: 12px;
#         color: gray;
#     }
#     </style>
#     <div class="footer">
#         <hr>
#         <p>© 2024 Proactive AI Lab</p>
#     </div>
#     """

# # Injecting the footer HTML into the sidebar
# st.sidebar.markdown(footer, unsafe_allow_html=True)


# Cognito JWKS URL

authenticator = CognitoAuthenticator(
    pool_id=AWS_USER_POOL_ID,
    app_client_id=AWS_APP_CLIENT_ID,
    app_client_secret=AWS_APP_CLIENT_SECRET,
    use_cookies=False,
)

is_logged_in = authenticator.login()
if not is_logged_in:
    st.stop()
else:
    user.update(authenticator=authenticator)

    # Specify what pages should be shown in the sidebar, and what their titles and icons
    # should be
    show_pages(
        [
            Page("app/pages/demos/Coffee_Assistant.py", "Coffee Assistant", "☕"),
            Page("app/pages/demos/Gym_Assistant_Test.py", "Gym Assistant", "🏋️"),
        ]
    )
