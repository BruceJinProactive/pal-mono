import streamlit as st

from app.auth import user


def user_ui():
    with st.sidebar:
        st.write("## User")
        st.info(f":office: Account: {user.account_name}")
        st.info(f":technologist: User: {user.email}")
        st.write(user)
