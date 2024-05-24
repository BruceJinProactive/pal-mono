import os

import streamlit as st
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

AWS_REGION = os.environ["AWS_REGION"]
AWS_USER_POOL_ID = os.environ["AWS_USER_POOL_ID"]
AWS_APP_CLIENT_ID = os.environ["AWS_APP_CLIENT_ID"]
AWS_APP_CLIENT_SECRET = os.environ["AWS_APP_CLIENT_SECRET"]

# Cognito JWKS URL
JWKS_URL = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{AWS_USER_POOL_ID}/.well-known/jwks.json"

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
    # Specify what pages should be shown in the sidebar, and what their titles and icons
    # should be
    show_pages(
        [
            Page("app/pages/demos/Gym_Assistant_Test.py", "Gym Assistant", "🏋️"),
        ]
    )
