import streamlit as st
from streamlit_cognito_auth import CognitoAuthenticator

from app.auth import AWS_APP_CLIENT_ID, AWS_APP_CLIENT_SECRET, AWS_USER_POOL_ID, user
from app.shared import footer_ui, set_page_config, user_ui

set_page_config()
st.title("Welcome to Proactive AI Lab!")
st.markdown("---")


def pages():
    home_page = st.Page("Home.py", title="Home", icon="🏠")
    console_pages = [
        st.Page("pages/console/Messages.py", title="Messages", icon="🖥️"),
        st.Page("pages/console/Demo.py", title="Demo", icon="💬"),
    ]
    pal_internal_pages = [
        st.Page("pages/internal/Account.py", title="[Internal]Account", icon="👤"),
    ]
    pal_root_pages = [
        st.Page("pages/internal/Root.py", title="[Root]Root", icon="⚠️"),
    ]

    pages = [home_page]
    if user.account_name is not None:
        pages.extend(console_pages)
    if user.account_name == "proactiveailab":
        pages.extend(pal_internal_pages)
        pages.extend(pal_root_pages)

    return pages


def dashboard():
    st.metric("Active Users", 1, 1)


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
    st.navigation(pages())
    user_ui()
    if st.sidebar.button("Logout", "logout_btn"):
        user.logout()
        authenticator.logout()
        st.experimental_rerun()
    footer_ui()
    dashboard()
