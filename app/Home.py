import streamlit as st
from st_pages import Page, show_pages
from streamlit_cognito_auth import CognitoAuthenticator

from app.auth import AWS_APP_CLIENT_ID, AWS_APP_CLIENT_SECRET, AWS_USER_POOL_ID, user
from app.shared import footer_ui, set_page_config, user_ui

set_page_config()

st.title("Welcome to Proactive AI Lab!")
st.markdown("---")


def pages():
    home_page = Page("app/Home.py", "Home", "🏠")
    test_pages = [
        Page("app/pages/test/services.py", "Services", "🚦"),
    ]
    demo_pages = [
        Page("app/pages/console/Demo.py", "Demo", "💬"),
    ]
    root_pages = [
        Page("app/pages/internal/Account.py", "Account", "👤"),
        Page("app/pages/internal/Root.py", "Root", "⚠️"),
    ]
    pages = [home_page]
    if user.account_name is not None:
        pages.extend(test_pages)
        pages.extend(demo_pages)
        pages.extend(root_pages)
    show_pages(pages)


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

    pages()

    user_ui()
    if st.sidebar.button("Logout", "logout_btn"):
        user.logout()
        authenticator.logout()
        st.experimental_rerun()
    footer_ui()
