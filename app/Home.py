import streamlit as st
from streamlit_cognito_auth import CognitoAuthenticator

from app.auth import AWS_APP_CLIENT_ID, AWS_APP_CLIENT_SECRET, AWS_USER_POOL_ID, user
from app.shared import set_page_config

set_page_config()


def pages():
    dashboard_pages = [
        st.Page(
            "pages/dashboard/dashboard.py",
            title="Dashboard",
            icon=":material/dashboard:",
            default=True,
        ),
    ]
    clients_pages = [
        st.Page(
            "pages/clients/onboard.py",
            title="Onboard",
            icon=":material/flight_takeoff:",
        ),
        st.Page(
            "pages/clients/accounts.py",
            title="Accounts",
            icon=":material/manage_accounts:",
        ),
        st.Page(
            "pages/clients/agents.py",
            title="Agents",
            icon=":material/smart_toy:",
        ),
        st.Page(
            "pages/clients/projects.py",
            title="Projects",
            icon=":material/album:",
        ),
        st.Page(
            "pages/clients/users.py",
            title="Users",
            icon=":material/group:",
        ),
        st.Page("pages/clients/live.py", title="Live", icon=":material/support_agent:"),
    ]
    development_pages = [
        st.Page(
            "pages/development/services.py",
            title="Services",
            icon=":material/room_service:",
        ),
        st.Page("pages/development/test.py", title="Test", icon=":material/quiz:"),
        st.Page(
            "pages/development/tools.py",
            title="Tools",
            icon=":material/pan_tool:",
        ),
        st.Page(
            "pages/development/utils.py",
            title="Utils",
            icon=":material/service_toolbox:",
        ),
    ]
    pages = {
        "Dashboard": dashboard_pages,
        "Clients": clients_pages,
        "Development": development_pages,
    }
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
