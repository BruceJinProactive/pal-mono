import streamlit as st
from streamlit_cognito_auth import CognitoAuthenticator

from app.auth import AWS_APP_CLIENT_ID, AWS_APP_CLIENT_SECRET, AWS_USER_POOL_ID, user
from app.shared import footer_ui, set_page_config, user_ui

set_page_config()


def pages():
    home_page = st.Page("Home.py", title="Home", icon="🏠")
    test_pages = [
        st.Page("pages/test/services.py", title="Services", icon="🚦"),
    ]
    demo_pages = [
        st.Page("pages/console/Demo.py", title="Demo", icon="💬"),
    ]
    root_pages = [
        st.Page("pages/internal/Account.py", title="Account", icon="👤"),
        st.Page("pages/internal/Root.py", title="Root", icon="⚠️"),
    ]
    pages = [home_page]
    if user.account_name is not None:
        pages.extend(test_pages)
        pages.extend(demo_pages)
        pages.extend(root_pages)
    return pages


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

    pg = st.navigation(pages())
    pg.run()

    user_ui()
    if st.sidebar.button("Logout", "logout_btn"):
        user.logout()
        authenticator.logout()
        st.rerun()
    footer_ui()
