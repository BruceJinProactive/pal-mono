#!/usr/bin/env python3

import os
import re
from collections import defaultdict


def parse_menu_file(file_path):
    """Parse a single menu item file and extract relevant information."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract item name and ID from first line
    first_line = content.split("\n")[0]
    name_match = re.match(r"# (.+) \(item_id: (\d+)\)", first_line)
    print(f"name_match: {name_match}")
    if not name_match:
        return None

    item_name = name_match.group(1)
    item_id = name_match.group(2)

    # Extract category
    category_match = re.search(r"\*\*Category:\*\* (.+)", content)
    category = category_match.group(1) if category_match else "Other"

    # Extract description
    desc_match = re.search(r"\*\*Description:\*\* (.+)", content)
    description = desc_match.group(1) if desc_match else ""

    # Extract prices
    prices = []
    price_section = re.search(r"## Prices\n(.*?)(?=\n##|\n$)", content, re.DOTALL)
    if price_section:
        price_lines = price_section.group(1).strip().split("\n")
        for line in price_lines:
            if line.strip().startswith("- "):
                # Parse price line like "- 12" (size_id: 1): $21.0"
                price_match = re.match(
                    r"- (.+?) \(size_id: \d+\): \$(.+)", line.strip()
                )
                if price_match:
                    size_name = price_match.group(1)
                    price = price_match.group(2)
                    prices.append(f"${price} ({size_name})")

    # Extract included modifiers
    included_items = []
    modifier_section = re.search(r"## Modifiers\n(.*?)$", content, re.DOTALL)
    if modifier_section:
        modifier_content = modifier_section.group(1)
        # Find all "#### Included" sections
        included_sections = re.findall(
            r"#### Included\n((?:- .+\n?)*)", modifier_content
        )
        for section in included_sections:
            lines = section.strip().split("\n")
            for line in lines:
                if line.strip().startswith("- "):
                    # Extract modifier name, removing modifier_id
                    modifier_match = re.match(
                        r"- (.+?) \(modifier_id: \d+\)", line.strip()
                    )
                    if modifier_match:
                        included_items.append(modifier_match.group(1))

    return {
        "name": item_name,
        "id": item_id,
        "category": category,
        "description": description,
        "prices": prices,
        "included": included_items,
    }


def format_menu_output(menu_items):
    """Format the menu items into the desired string format matching current.txt exactly."""
    # Group items by category
    categories = defaultdict(list)
    for item in menu_items:
        categories[item["category"]].append(item)
    # print(f"categories: {categories}")
    # Define category order to match current.txt format
    # category_order = ["Salads & Snacks", "Drinks & Desserts", "Pizzas", "Sides"]

    output_parts = []

    for category in categories.keys():
        # if category not in categories:
        #     continue

        output_parts.append(f"## {category}")

        for item in categories[category]:
            # Format item name with description if available
            if item["description"]:
                name_line = f"### {item['name']} - {item['description']}"
            else:
                name_line = f"### {item['name']}"
            output_parts.append(name_line)

            # Format prices exactly like current.txt
            if item["prices"]:
                if len(item["prices"]) == 1:
                    # Single price - remove size info for simple display
                    price_str = item["prices"][0]
                    if "(" in price_str:
                        # Extract just the price value for single items
                        price_val = price_str.split(" (")[0]
                        output_parts.append(f"Prices: {price_val}")
                    else:
                        output_parts.append(f"Prices: {price_str}")
                else:
                    # Multiple prices - keep size information
                    price_parts = []
                    for price in item["prices"]:
                        if "(" in price:
                            price_val, size_info = price.split(" (", 1)
                            size_info = size_info.rstrip(")")
                            price_parts.append(f"{price_val} ({size_info})")
                        else:
                            price_parts.append(price)
                    output_parts.append(f"Prices: {', '.join(price_parts)}")

            # Format included items
            if item["included"]:
                included_str = ", ".join(item["included"])
                output_parts.append(f"Included: {included_str}")

            output_parts.append("")  # Empty line between items

    # Join with \n and escape newlines to match current.txt format
    result = "\\n".join(output_parts)
    # Escape quotes with backslashes
    result = result.replace('"', '\\"')
    return result


def concatenate_menu_files(menu_dir, output_file_path):
    """
    Processes all menu files in a directory and writes a single formatted menu file.
    Returns the number of items processed and a preview of the output.
    """
    if not os.path.exists(menu_dir):
        print(f"Directory {menu_dir} not found!")
        return 0, None

    menu_items = []

    # Process all txt files in the directory
    for filename in os.listdir(menu_dir):
        if filename.endswith(".txt") and filename.startswith("item_"):
            file_path = os.path.join(menu_dir, filename)
            item_data = parse_menu_file(file_path)
            if item_data:
                menu_items.append(item_data)

    # Sort items by category and name for consistent output
    menu_items.sort(key=lambda x: (x["category"], x["name"]))

    # Generate formatted output
    formatted_output = format_menu_output(menu_items)

    # Write to output file
    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write(formatted_output)

    num_items = len(menu_items)
    print(f"Processed {num_items} menu items")
    print(f"Formatted menu saved to '{output_file_path}'")

    preview = formatted_output[:200] + "..."

    return num_items, preview


def main():
    """Main function to process all menu files."""
    menu_dir = "menu/Adora_UQ5ZT/output_UQ5ZT_with_ids"
    output_file = "menu/Adora_UQ5ZT/menu_formatted_old_structure.txt"

    if not os.path.exists(os.path.dirname(output_file)):
        os.makedirs(os.path.dirname(output_file))

    num_items, preview = concatenate_menu_files(menu_dir, output_file)

    if preview:
        print("\nFirst 200 characters of output:")
        print(preview)


if __name__ == "__main__":
    main()
