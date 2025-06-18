import os
import re
from collections import defaultdict


def parse_menu_file(file_path):
    """Parse a single menu item file and extract relevant information."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract item name and ID from first line
    first_line = content.split("\n")[0]
    name_match = re.match(r"# (.+)", first_line)
    if not name_match:
        return None

    item_name = name_match.group(1)

    # Extract category
    category_match = re.search(r"\*\*Category:\*\* (.+)", content)
    category = category_match.group(1) if category_match else "Other"
    # Replace "Apps" with "Appetizers"
    if category == "Apps":
        category = "Appetizers"

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
                # Parse price line like "- 12 Slices) (3-4 people: $8.99"
                price_match = re.match(r"- (.+?): \$(.+)", line.strip())
                if price_match:
                    size_name = price_match.group(1)
                    price = price_match.group(2)
                    prices.append(f"${price} ({size_name})")

    # Extract modifiers
    modifiers = defaultdict(lambda: {"included": [], "optional": []})

    # Split content by main sections (##)
    sections = re.split(r"\n## ", content)
    for section in sections:
        if section.startswith("Modifiers"):
            # Split by modifier categories (###)
            category_sections = re.split(r"\n### ", section)
            for cat_section in category_sections[1:]:  # Skip the "Modifiers" header
                if not cat_section.strip():
                    continue

                # Get category name and content
                cat_lines = cat_section.split("\n", 1)
                if len(cat_lines) < 2:
                    continue

                category_name = cat_lines[0].strip()
                cat_content = cat_lines[1]

                # Find all sections starting with ####
                modifier_sections = re.findall(
                    r"#### (Included|Optional)\n((?:- .+\n?)*)", cat_content
                )
                for modifier_type, mod_content in modifier_sections:
                    # Extract items
                    items = [
                        line.strip()[2:]
                        for line in mod_content.strip().split("\n")
                        if line.strip()
                    ]

                    if modifier_type == "Included":
                        modifiers[category_name]["included"].extend(items)
                    elif modifier_type == "Optional":
                        modifiers[category_name]["optional"].extend(items)

    return {
        "name": item_name,
        "category": category,
        "description": description,
        "prices": prices,
        "modifiers": dict(modifiers),
    }


def format_menu_output(menu_items):
    """Format the menu items into the desired string format."""
    # Group items by category
    categories = defaultdict(list)
    for item in menu_items:
        categories[item["category"]].append(item)

    output_parts = []

    for category, items in categories.items():
        output_parts.append(category)

        for item in items:
            # Format item name with description if available
            if item["description"]:
                name_line = f"\t{item['name']} - {item['description']}"
            else:
                name_line = f"\t{item['name']}"
            output_parts.append(name_line)

            # Format prices
            if item["prices"]:
                price_parts = []
                for price in item["prices"]:
                    if "(" in price:
                        price_val, size_info = price.split(" (", 1)
                        size_info = size_info.rstrip(")")
                        price_parts.append(f"{price_val} ({size_info})")
                    else:
                        price_parts.append(price)
                output_parts.append(f"\t\tPrices: {', '.join(price_parts)}")

            # Format modifiers
            if item["modifiers"]:
                output_parts.append("\t\tModifiers:")
                for modifier_category, modifier_data in item["modifiers"].items():
                    output_parts.append(f"\t\t\t{modifier_category}:")
                    if modifier_data["included"]:
                        output_parts.append(
                            f"\t\t\t\tIncluded: {', '.join(modifier_data['included'])}"
                        )
                    if modifier_data["optional"]:
                        output_parts.append(
                            f"\t\t\t\tOptional: {', '.join(modifier_data['optional'])}"
                        )

            output_parts.append("")  # Empty line between items

    # Join with actual newlines
    result = "\n".join(output_parts)
    # Escape quotes with backslashes
    result = result.replace('"', '\\"')
    return result


def concatenate_menu_files(menu_dir, output_file_path):
    """
    Processes all menu files in a directory and writes a single formatted menu file.
    Returns the number of items processed.
    """
    if not os.path.exists(menu_dir):
        print(f"Directory {menu_dir} not found!")
        return 0

    menu_items = []

    # Process all txt files in the directory
    for filename in os.listdir(menu_dir):
        if filename.endswith(".txt"):
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

    print(f"Processed {len(menu_items)} menu items")
    print(f"Formatted menu saved to '{output_file_path}'")
    # Return a slice of the formatted output for preview
    return formatted_output[:200] + "..."


def main():
    """Main function to process all menu files."""
    menu_dir = "menu/pizza_guys/output_UGDX4_no_ids"
    output_file = "menu/pizza_guys/menu_formatted.txt"

    if not os.path.exists(os.path.dirname(output_file)):
        os.makedirs(os.path.dirname(output_file))

    preview = concatenate_menu_files(menu_dir, output_file)

    if preview:
        print("\nFirst 200 characters of output:")
        print(preview)


if __name__ == "__main__":
    main()
