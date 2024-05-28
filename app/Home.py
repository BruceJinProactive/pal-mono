import streamlit as st
from st_pages import Page, show_pages
from streamlit_cognito_auth import CognitoAuthenticator

from app.auth import (
    AWS_APP_CLIENT_ID,
    AWS_APP_CLIENT_SECRET,
    AWS_USER_POOL_ID,
    footer_ui,
    user,
    user_ui,
)

st.set_page_config(
    page_title="Proactive AI Console",
    page_icon=":control-knobs:",
)

st.title("Welcome to Proactive AI!")
st.markdown("---")


def pages():
    home_page = Page("app/Home.py", "Home", "🏠")
    customer_specific_pages = [
        Page("app/pages/customer/Training.py", "Training", "📖"),
    ]
    pal_internal_pages = [
        Page("app/pages/admin/Account.py", "[Internal]Account", "👤"),
        # Demo pages
        Page("app/pages/demos/Coffee_Assistant.py", "[Internal]Coffee", "☕"),
        Page("app/pages/demos/Gym_Assistant_Test.py", "[Internal]Gym", "🏋️"),
    ]
    pal_root_pages = [
        Page("app/pages/admin/Root.py", "[Root]Root", "⚠️"),
    ]
    pages = [home_page]
    if user.account_name is not None:
        pages.extend(customer_specific_pages)
    if user.account_name == "proactiveailab":
        pages.extend(pal_internal_pages)
    if user.account_name == "root":
        pages.extend(pal_internal_pages)
        pages.extend(pal_root_pages)
    show_pages(pages)


def dashboard():
    st.metric("Active Users", 1000, 300)


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

    dashboard()
