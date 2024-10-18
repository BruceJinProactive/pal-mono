# import json
# from os import getenv

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

# from ai.tools.booking_tools import BookingTools
# from ai.tools.ordering_tools import OrderingTools
from app.auth import user
from db.session import get_db

st.title("Tools")

db = next(get_db())

(ordering_tools_tab, booking_tools_tab) = st.tabs(["Ordering Tools", "Booking Tools"])


# def ordering_tools_tab_content():
#     st.write("# Ordering Tools")
#     toolkit = OrderingTools(
#         {
#             "type": "adora",
#             "api_key": getenv("ADORA_POS_API_KEY"),
#             "api_secret": getenv("ADORA_POS_API_SECRET"),
#         }
#     )

#     st.write("### Add to Order")
#     item_name = st.text_input("Item Name", value="Big Sur")
#     size = st.text_input("Size", value='18"')
#     quantity = st.number_input("Quantity", value=1)
#     modifications = st.text_input(
#         "Modifications", value="Extra Garlic, Light Mushrooms", help="Separate by comma"
#     )
#     if st.button("Add to Order"):
#         retval = toolkit.add_to_order(
#             item_name, size, int(quantity), modifications.split(",")
#         )
#         st.write(retval)

#     st.write("### Place Order")
#     if st.button("Place Order"):
#         retval = toolkit.place_order()
#         st.write(retval)


# def booking_tools_tab_content():
#     st.write("# Booking Tools")
#     toolkit = BookingTools({
#         type: "mindzero",
#     })

#     st.write("### Get Class Sessions")
#     num_days = st.number_input("Number of Days", value=7)
#     if st.button("Get Class Sessions"):
#         retval = toolkit.get_class_sessions(int(num_days))
#         st.json(json.loads(retval))


def main() -> None:
    st.write("## In development")
    st.write("This page is still in development.")
    # with ordering_tools_tab:
    #     ordering_tools_tab_content()
    # with booking_tools_tab:
    #     booking_tools_tab_content()


if user.is_logged_in:
    main()
else:
    switch_page("home")
