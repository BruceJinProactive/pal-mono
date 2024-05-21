import os

import streamlit as st
from streamlit_cognito_auth import CognitoAuthenticator

st.set_page_config(
    page_title="Account Test",
    page_icon=":key:",
)
st.title("Account Test")

aws_user_pool_id = os.environ["AWS_USER_POOL_ID"]
aws_app_client_id = os.environ["AWS_APP_CLIENT_ID"]
aws_app_client_secret = os.environ["AWS_APP_CLIENT_SECRET"]

authenticator = CognitoAuthenticator(
    pool_id=aws_user_pool_id,
    app_client_id=aws_app_client_id,
    app_client_secret=aws_app_client_secret,
    use_cookies=False,
)

is_logged_in = authenticator.login()
if not is_logged_in:
    st.stop()
else:
    st.write("You are logged in!")

    st.write(authenticator.get_username())
    st.write(authenticator.get_credentials())


def logout():
    print("Logout in example")
    authenticator.logout()


with st.sidebar:
    st.text(f"Welcome,\n{authenticator.get_email()}")
    st.button("Logout", "logout_btn", on_click=logout)
