import json

menu = {}
with open("data/pizza/jsons/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
    menu = json.load(read_f)

for item in menu["items"]:
    if not all(
        order_type["sizes"] == item["order_types"][0]["sizes"]
        for order_type in item["order_types"]
    ):
        print(item["name"])
