import streamlit as st

from app.auth import user


def set_page_config():
    st.set_page_config(
        page_title="Proactive AI Lab",
        page_icon="https://media.licdn.com/dms/image/D560BAQG_oe45276rYQ/company-logo_100_100/0/1717434128276?e=1725494400&v=beta&t=IfK9h8vL1zMVN0eLsAqcDnCvxHmRJis0J1J_SsGcC4s",
    )


def set_account(account_name):
    st.session_state["account_name"] = account_name
    if "project_name" in st.session_state:
        st.session_state.pop("project_name")
    if "assistant_id" in st.session_state:
        st.session_state.pop("assistant_id")


def user_ui():
    with st.sidebar:
        st.write("## User")
        st.info(f":technologist: User: {user.email}")
        # st.write(user)


def footer_ui():
    footer = """
        <style>
        .sidebar .sidebar-content {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
        }
        .footer {
            text-align: center;
            padding: 10px 0;
            font-size: 12px;
            color: gray;
        }
        </style>
        <div class="footer">
            <hr>
            <p>© 2024 Proactive AI Lab</p>
        </div>
        """

    st.sidebar.markdown(footer, unsafe_allow_html=True)
