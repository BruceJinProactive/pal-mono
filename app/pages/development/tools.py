import json

import streamlit as st
from streamlit_extras.switch_page_button import switch_page

from ai.assistants.gym_assistant import BookingTools
from ai.assistants.pizza_assistant import PizzaMyHeartTools
from ai.tools.ordering_tools import OrderingTools
from app.auth import user
from db.session import get_db

st.title("Tools")

db = next(get_db())

(ordering_tools_tab, booking_tools_tab, pizza_my_heart_tools_tab) = st.tabs(
    ["Ordering Tools", "Booking Tools", "Pizza My Heart Tools"]
)


def ordering_tools_tab_content():
    st.write("# Ordering Tools")
    toolkit = OrderingTools()

    st.write("### Add to Order")
    item_name = st.text_input("Item Name", value="Big Sur")
    size = st.text_input("Size", value='18"')
    quantity = st.number_input("Quantity", value=1)
    modifications = st.text_input(
        "Modifications", value="Extra Garlic, Light Mushrooms", help="Separate by comma"
    )
    if st.button("Add to Order"):
        retval = toolkit.add_to_order(
            item_name, size, int(quantity), modifications.split(",")
        )
        st.write(retval)

    st.write("### Place Order")
    if st.button("Place Order"):
        retval = toolkit.place_order()
        st.write(retval)


def booking_tools_tab_content():
    st.write("# Booking Tools")
    toolkit = BookingTools()

    st.write("### Get Class Sessions")
    num_days = st.number_input("Number of Days", value=7)
    if st.button("Get Class Sessions"):
        retval = toolkit.get_class_sessions(int(num_days))
        st.json(json.loads(retval))


def pizza_my_heart_tools_tab_content():
    st.write("# Pizza My Heart Tools")
    toolkit = PizzaMyHeartTools()

    st.write("### Pizza Calculator")
    num_meat_and_veggie_lovers = st.number_input(
        "Number of Meat and Veggie Lovers", value=0
    )
    num_vegetarian = st.number_input("Number of Vegetarians", value=0)
    num_vegan = st.number_input("Number of Vegans", value=0)
    num_kids = st.number_input("Number of Kids", value=0)
    if st.button("Calculate Pizzas"):
        retval = toolkit.pizza_calculator(
            str(num_meat_and_veggie_lovers),
            str(num_vegetarian),
            str(num_vegan),
            str(num_kids),
        )
        try:
            st.json(json.loads(retval))
        except json.JSONDecodeError:
            st.write(retval)


def main() -> None:
    with ordering_tools_tab:
        ordering_tools_tab_content()
    with booking_tools_tab:
        booking_tools_tab_content()
    with pizza_my_heart_tools_tab:
        pizza_my_heart_tools_tab_content()


if user.is_logged_in:
    main()
else:
    switch_page("home")
