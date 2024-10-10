import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from app.auth import user
from db.session import get_db
from utils.secret import get_client_secret

st.title("Services")

db = next(get_db())

(secret_tab,) = st.tabs(["Secret"])


def main() -> None:
    with secret_tab:
        st.write("### get_client_secret")

        secret_key = st.text_input("Secret Key")

        if st.button("Get Client Secret"):
            secret_value = get_client_secret(secret_key)
            masked_secret_value = (
                secret_value[:2] + "*" * (len(secret_value) - 4) + secret_value[-2:]
            )
            st.write(masked_secret_value)


if user.is_logged_in:
    main()
else:
    switch_page("home")
