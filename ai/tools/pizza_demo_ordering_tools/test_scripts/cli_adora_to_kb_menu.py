import json

adora_menu = {}
with open("data/pizza/Pizza_My_Heart_Adora_Menu.json", "r") as read_f:
    adora_menu = json.load(read_f)

menu: dict = {"menuItems": {}, "availableModifiers": []}

size_mapping = {}
for size in adora_menu["sizes"]:
    size_mapping[size["size_id"]] = size["name"]
size_mapping.pop(0)

available_modifiers = set()
for modifier in adora_menu["modifiers"]:
    available_modifiers.add(modifier["name"])
menu["availableModifiers"] = list(available_modifiers)

for item in adora_menu["items"]:
    item_name = item["name"]
    item_description = item["description"]
    item_sizes = {}
    for size in item["prices"]:
        if size["size_id"] in size_mapping:
            item_sizes[size_mapping[size["size_id"]]] = "$" + str(size["price"])
    menu["menuItems"][item_name] = {
        "description": item_description,
        "image": None,
        "sizes": item_sizes,
    }


with open("pmh_menu_knowledge_base.json", "w") as write_f:
    json.dump(menu, write_f, ensure_ascii=False, indent=4)
