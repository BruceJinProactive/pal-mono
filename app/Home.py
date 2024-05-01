import streamlit as st

from phi.tools.streamlit.components import check_password

st.set_page_config(
    page_title="Proactive AI Demos",
    page_icon=":smile:",
)
st.title("Welcome to Proactive AI Demos!")


def main() -> None:
    st.markdown("---")
    st.markdown("## Select a Demo to Start:")
    st.markdown("#### :coffee: Coffee Assistant")
    st.markdown("A conversational AI assistant for a coffee shop")

    st.sidebar.success("Select demo from above")


# if check_password():
#     main()

main()
