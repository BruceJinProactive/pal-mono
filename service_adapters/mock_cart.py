import json


def add_mock_cart(user_id, pizza_item):
    """
    For now just append the pizza item to the cart.json file.
    """

    cart = {}

    with open("cart.json", "r") as read_f:
        cart = json.load(read_f)

    def get_price_of_pizza(pizza_name, quantity, size):
        """
        Get price of the pizza based on the menu.
        For now, only support award winning pizzas.
        """
        size_num = 0
        if size == "small":
            size_num = '12"'
        elif size == "medium":
            size_num = '14"'
        elif size == "large":
            size_num = '18"'

        with open("data/pizza/jsons/Pizza_My_Heart_Menu.json") as menu_f:
            menu = json.load(menu_f)
            for pizza in menu["Pizza My Heart Menu"]["Award Winning Pizzas"]:
                if pizza["name"] == pizza_name:
                    return int(quantity) * float(pizza["sizes"][size_num][1:])

            for pizza in menu["Pizza My Heart Menu"]["Specialty Pizzas with Meat"]:
                if pizza["name"] == pizza_name:
                    return int(quantity) * float(pizza["sizes"][size_num][1:])

            for pizza in menu["Pizza My Heart Menu"][
                "Vegan & Vegetarian Specialty Pizzas"
            ]:
                if pizza["name"] == pizza_name:
                    return int(quantity) * float(pizza["sizes"][size_num][1:])

        return 0

    def convert_pizza_name(pizza_name):
        """
        Convert the pizza name to the format in the menu.
        Simple lower case + remove spaces for now.
        """

        def lower_alnum_only(s):
            return "".join(c for c in s if c.isalnum()).lower()

        with open("data/pizza/jsons/Pizza_My_Heart_Menu.json") as menu_f:
            menu = json.load(menu_f)

            for pizza in menu["Pizza My Heart Menu"]["Award Winning Pizzas"]:
                if lower_alnum_only(pizza["name"]) == lower_alnum_only(pizza_name):
                    return pizza["name"]

            for pizza in menu["Pizza My Heart Menu"]["Specialty Pizzas with Meat"]:
                if lower_alnum_only(pizza["name"]) == lower_alnum_only(pizza_name):
                    return pizza["name"]

            for pizza in menu["Pizza My Heart Menu"][
                "Vegan & Vegetarian Specialty Pizzas"
            ]:
                if lower_alnum_only(pizza["name"]) == lower_alnum_only(pizza_name):
                    return pizza["name"]

        return ""

    # create user
    if user_id not in cart:
        cart[user_id] = {"price": 0, "list_of_cart_items": []}

    pizza_item["size"] = pizza_item["size"].lower()
    pizza_item["pizza_name"] = convert_pizza_name(pizza_item["pizza_name"])

    # return 0 indicating item not on menu
    if not pizza_item["pizza_name"]:
        return 0

    cart[user_id]["list_of_cart_items"].append(pizza_item)
    cart[user_id]["price"] += get_price_of_pizza(
        pizza_item["pizza_name"], pizza_item["quantity"], pizza_item["size"]
    )

    with open("cart.json", "w", encoding="utf-8") as f:
        json.dump(cart, f, ensure_ascii=False, indent=4)

    return 1


def get_mock_cart(user_id):
    cart = {}

    with open("cart.json", "r") as read_f:
        cart = json.load(read_f)

    if user_id not in cart:
        cart[user_id] = {"price": 0, "list_of_cart_items": []}

    return cart[user_id]


def order_mock_cart(user_id):
    """
    Placeholder for now: Reset the cart.json file.
    """

    cart = {}

    with open("cart.json", "r") as read_f:
        cart = json.load(read_f)

    if user_id not in cart:
        cart[user_id] = {"price": 0, "list_of_cart_items": []}

    cart[user_id]["price"] = 0
    cart[user_id]["list_of_cart_items"] = []

    with open("cart.json", "w", encoding="utf-8") as f:
        json.dump(cart, f, ensure_ascii=False, indent=4)
