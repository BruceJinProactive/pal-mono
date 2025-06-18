import json
import os
import re

########################################################
# Change these to match your store
STORE_ID = "UGDX4"
STORE_MENU_DIR = "pizza_guys"

FILE = f"menu/{STORE_MENU_DIR}/{STORE_ID}.json"
WITH_IDS = True  # Include modifier, item ids, etc.
OUTPUT_DIR = (
    f"menu/{STORE_MENU_DIR}/output_{STORE_ID}_{'with' if WITH_IDS else 'no'}_ids"
)
########################################################


def get_category(categories, category_id):
    for cat in categories:
        if cat.get("category_id") == category_id:
            return cat.get("name")
    return "Unknown"


def get_size_description(sizes, size_id):
    # Sometimes sizes may be duplicated; return the first matching description.
    for s in sizes:
        if s.get("size_id") == size_id:
            return s.get("description")
    return f"Size {size_id}"


def get_modifier_group_name(modifier_groups, group_id):
    for mg in modifier_groups:
        if mg.get("modifier_group_id") == group_id:
            return mg.get("name")
    return f"Group {group_id}"


def generate_text_files_from_json(json_data, output_dir, with_ids=False):
    """Processes menu JSON data and creates individual text files for each item."""
    categories = json_data.get("categories", [])
    sizes = json_data.get("sizes", [])
    global_modifier_groups = json_data.get("modifier_groups", [])

    # Create dictionary of modifiers for easy lookup
    modifiers = {}
    for modifier in json_data.get("modifiers", []):
        modifier_id = modifier["modifier_id"]
        modifiers[modifier_id] = modifier["name"]

    for item in json_data.get("items", []):
        item_id = item.get("item_id")
        item_name = item.get("name", f"Item {item_id}")
        item_category_id = item.get("item_category_id")
        category_name = get_category(categories, item_category_id)
        description = item.get("description", "")

        lines = []
        # Title
        if with_ids:
            lines.append(f"# {item_name} (item_id: {item_id})")
        else:
            lines.append(f"# {item_name}")

        lines.append("")
        lines.append(f"**Category:** {category_name}")

        lines.append("")
        lines.append(f"**Description:** {description}")
        lines.append("")

        ### Get order_types section ###
        # This is a list of order types that the item is available in. We use this to
        # get the possible allowed sizes.
        order_types = item["order_types"]
        allowed_size_ids = set()
        if order_types:
            for order_type in order_types:
                for size in order_type["sizes"]:
                    size_id = size["size_id"]
                    allowed_size_ids.add(size_id)
        if category_name == "Apps":
            print(f"Allowed size ids: {allowed_size_ids}")

        ### Prices section ###
        # Here we create the prices section. We ONLY include prices for allowed sizes.
        prices = item.get("prices", [])
        if prices:
            lines.append("## Prices")
            for p in prices:
                size_id = p["size_id"]
                if size_id in allowed_size_ids:
                    price = p.get("price")
                    size_desc = get_size_description(sizes, size_id)

                    if with_ids:
                        lines.append(f"- {size_desc} (size_id: {size_id}): ${price}")
                    else:
                        lines.append(f"- {size_desc}: ${price}")

            lines.append("")

        # Modifiers section
        modifier_groups_item = item.get("modifier_groups", [])
        if modifier_groups_item:
            lines.append("## Modifiers")
            for group in modifier_groups_item:
                group_id = group.get("modifier_group_id")
                group_name = get_modifier_group_name(global_modifier_groups, group_id)
                lines.append(f"### {group_name}")

                # Separate modifiers into "Included" (default True) and "Optional" (default False)
                included = []
                optional = []
                for mod in group.get("modifiers", []):
                    if mod.get("default"):
                        included.append(mod)
                    else:
                        optional.append(mod)
                if included:
                    lines.append("#### Included")
                    for mod in included:
                        modifier_name = modifiers[mod.get("modifier_id")]

                        if with_ids:
                            lines.append(
                                f"- {modifier_name} (modifier_id: {mod.get('modifier_id')})"
                            )
                        else:
                            lines.append(f"- {modifier_name}")

                if optional:
                    lines.append("#### Optional")
                    for mod in optional:
                        modifier_name = modifiers[mod.get("modifier_id")]

                        if with_ids:
                            lines.append(
                                f"- {modifier_name} (modifier_id: {mod.get('modifier_id')})"
                            )
                        else:
                            lines.append(f"- {modifier_name}")

                lines.append("")

        # Join all lines into one markdown string
        markdown = "\n".join(lines)

        # Write each markdown file (e.g., using item_id in the filename)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        item_name_sanitized = re.sub(r"[^\w\s]", "", item_name)
        filename = f"{output_dir}/item_{item_id}_{item_name_sanitized}.txt"
        with open(filename, "w") as outfile:
            outfile.write(markdown)
        print(f"Created {filename}")


def main():
    with open(FILE) as f:
        data = json.load(f)

    generate_text_files_from_json(data, OUTPUT_DIR, WITH_IDS)


if __name__ == "__main__":
    main()
