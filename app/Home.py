import streamlit as st

st.set_page_config(
    page_title="Proactive AI Console",
    page_icon=":control-knobs:",
)


st.title("Welcome to Proactive AI!")

st.markdown("---")

# # Sidebar Footer
# footer = """
#     <style>
#     .sidebar .sidebar-content {
#         display: flex;
#         flex-direction: column;
#         justify-content: space-between;
#         height: 100%;
#     }
#     .footer {
#         text-align: center;
#         padding: 10px 0;
#         font-size: 12px;
#         color: gray;
#     }
#     </style>
#     <div class="footer">
#         <hr>
#         <p>© 2024 Proactive AI Lab</p>
#     </div>
#     """

# # Injecting the footer HTML into the sidebar
# st.sidebar.markdown(footer, unsafe_allow_html=True)
