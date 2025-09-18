"""
Square menu text formatting for knowledge base indexing.

Generates per item documents (with IDs) and a consolidated menu prompt with Square categories.
"""

from typing import Any, Dict, List, Tuple


def generate_item_text(
    item: Dict[str, Any], with_ids: bool = True, location_id: str | None = None
) -> Tuple[str, str]:
    """Generate a single item document text and return with the item name.

    The document includes IDs to make it useful for debugging and indexing.
    """
    lines: List[str] = []

    name = item.get("item_name", "Unknown Item")
    item_id = item.get("item_id", "")
    lines.append("=" * 60)
    lines.append(f"ITEM: {name}")
    lines.append("=" * 60)
    lines.append("")

    if with_ids:
        lines.append("IDS:")
        lines.append(f"* Item ID: {item_id}")
        if location_id:
            lines.append(f"* Location ID: {location_id}")
        lines.append("")

    # Basic info
    lines.append("BASIC INFORMATION:")
    lines.append(f"* Item Name: {name}")
    desc = (item.get("description") or "").strip().replace("*", "").replace("**", "")
    if desc:
        desc_lines = [ln.strip() for ln in desc.split("\n") if ln.strip()]
        if desc_lines:
            lines.append(f"* Description: {', '.join(desc_lines)}")
    lines.append("")

    # Variations
    lines.append("VARIATIONS:")
    for var in item.get("variations", []) or []:
        if with_ids:
            lines.append(f"* Variation ID: {var.get('variation_id','')}")
        var_name = var.get("variation_name") or "Regular"
        lines.append(f"  - Name: {var_name}")
        lines.append(f"  - Price: {var.get('price','')}")
        lines.append("")

    # Categories
    cats = item.get("categories", []) or []
    if cats:
        lines.append("CATEGORIES:")
        for cat in cats:
            if with_ids:
                lines.append(f"* Category ID: {cat.get('category_id','')}")
            lines.append(f"  - Name: {cat.get('category_name','')}")
            lines.append(f"  - Ordinal: {cat.get('ordinal',0)}")
            lines.append("")

    # Modifiers
    mod_lists = item.get("modifier_lists", []) or []
    if mod_lists:
        lines.append("MODIFIER LISTS:")
        for ml in mod_lists:
            if with_ids:
                lines.append(f"* Modifier List ID: {ml.get('modifier_list_id','')}")
            lines.append(f"  - Name: {ml.get('name') or 'Options'}")
            lines.append(f"  - Selection Type: {ml.get('selection_type','SINGLE')}")
            lines.append(f"  - Min Selected: {ml.get('min_selected',0)}")
            lines.append(f"  - Max Selected: {ml.get('max_selected',1)}")
            lines.append("  - Modifiers:")
            for mod in ml.get("modifiers", []) or []:
                if with_ids:
                    lines.append(f"    * Modifier ID: {mod.get('modifier_id','')}")
                lines.append(f"      - Name: {mod.get('name','')}")
                amt = mod.get("price_amount", 0)
                cur = mod.get("price_currency", "USD")
                if amt > 0:
                    price_str = f"${amt/100:.2f}" if cur == "USD" else f"{amt} {cur}"
                    lines.append(f"      - Price: +{price_str}")
                else:
                    lines.append("      - Price: Free")
                lines.append("")
            lines.append("")

    return "\n".join(lines), name


def format_consolidated_menu(items: List[Dict[str, Any]]) -> str:
    """Create a single customer-facing menu text from extracted items.

    Mirrors the structure of the manager’s demo script for readability.
    """
    out: List[str] = []
    for item in items:
        variations = item.get("variations", []) or []
        name = item.get("item_name", "Unknown Item")
        # Single or multiple variations
        if len(variations) == 1:
            var = variations[0]
            display_name = (
                f"{name} - {var['variation_name']}"
                if var.get("variation_name")
                else name
            )
            out.append(f"* {display_name} ({var.get('price','')})")
        else:
            out.append(f"* {name}")
            for var in variations:
                if var.get("variation_name"):
                    out.append(f"** {var['variation_name']} ({var.get('price','')})")
                else:
                    out.append(f"** Regular ({var.get('price','')})")

        # Categories
        cats = item.get("categories", []) or []
        if cats:
            cat_names = [c.get("category_name", "") for c in cats]
            out.append(f"** Categories: {', '.join(cat_names)}")

        # Description
        desc = (
            (item.get("description") or "").strip().replace("*", "").replace("**", "")
        )
        if desc:
            desc_lines = [ln.strip() for ln in desc.split("\n") if ln.strip()]
            if desc_lines:
                out.append(f"** {', '.join(desc_lines)}")

        # Modifier lists
        mod_lists = item.get("modifier_lists", []) or []
        if mod_lists:
            out.append("** MODIFIER LISTS:")

            def sort_key(ml: Dict[str, Any]):
                import re

                name = ml.get("name") or "Options"
                m = re.match(r"^(\d+)", name)
                return int(m.group(1)) if m else 10**9

            for ml in sorted(mod_lists, key=sort_key):
                if not ml.get("modifiers"):
                    continue
                display_name = ml.get("name") or "Options"
                # Normalize selection bounds
                try:
                    min_sel = int(ml.get("min_selected") or 0)
                except (TypeError, ValueError):
                    min_sel = 0

                max_raw = ml.get("max_selected")
                max_int: int | None
                try:
                    max_int = int(max_raw) if max_raw is not None else None
                except (TypeError, ValueError):
                    max_int = None

                # Detect unbounded maximums commonly encoded as None, 0, "inf", or float('inf')
                unbounded = False
                if max_int is None:
                    unbounded = True
                elif isinstance(max_raw, str) and max_raw.lower() in {
                    "inf",
                    "infinite",
                    "infinity",
                    "unbounded",
                }:
                    unbounded = True
                elif isinstance(max_raw, (int, float)) and float(max_raw) == float(
                    "inf"
                ):
                    unbounded = True
                elif max_int == 0:  # Some APIs use 0 to mean no max
                    unbounded = True

                # Selection info
                if unbounded:
                    selection = (
                        "(Optional, select any)"
                        if min_sel == 0
                        else f"(Select at least {min_sel})"
                    )
                elif max_int is not None and min_sel == max_int:
                    selection = (
                        "(Optional)" if min_sel == 0 else f"(Select exactly {min_sel})"
                    )
                else:
                    selection = f"(Select {min_sel}-{max_int})"

                out.append(f"*** {display_name}: {selection}")

                # Options on one line
                options: List[str] = []
                for md in ml.get("modifiers", []) or []:
                    amt = md.get("price_amount", 0)
                    cur = md.get("price_currency", "USD")
                    if amt > 0:
                        price_str = (
                            f" (+${amt/100:.2f})"
                            if cur == "USD"
                            else f" (+{amt} {cur})"
                        )
                        options.append(f"{md.get('name','')}{price_str}")
                    else:
                        options.append(md.get("name", ""))
                out.append(f"**** {', '.join(options)}")
        out.append("")

    # Stats section expanded to match the reference builder
    out.append("=" * 60)
    out.append("STATISTICS")
    out.append("=" * 60)
    out.append(f"Total items: {len(items)}")

    taxable_items = [it for it in items if it.get("is_taxable", True)]
    non_taxable_items = [it for it in items if not it.get("is_taxable", True)]
    out.append(f"Taxable items: {len(taxable_items)}")
    out.append(f"Non-taxable items: {len(non_taxable_items)}")
    out.append("")

    # Category statistics
    category_item_count: Dict[str, int] = {}
    category_name_to_ids: Dict[str, set] = {}
    all_category_names: List[str] = []

    for it in items:
        for cat in it.get("categories", []) or []:
            cat_name = cat.get("category_name", "")
            cat_id = cat.get("category_id", "")
            all_category_names.append(cat_name)
            category_item_count[cat_name] = category_item_count.get(cat_name, 0) + 1
            if cat_name not in category_name_to_ids:
                category_name_to_ids[cat_name] = set()
            category_name_to_ids[cat_name].add(cat_id)

    unique_category_names = set(all_category_names)
    total_category_ids = sum(len(ids) for ids in category_name_to_ids.values())
    out.append(f"Total unique category names: {len(unique_category_names)}")
    out.append(f"Total category IDs: {total_category_ids}")
    out.append("")

    out.append("ITEMS PER CATEGORY:")
    for cat_name in sorted(category_item_count.keys()):
        out.append(f"  {cat_name}: {category_item_count[cat_name]} items")
    out.append("")

    out.append("CATEGORY NAMES WITH MULTIPLE IDS:")
    duplicate_names = {
        n: len(ids) for n, ids in category_name_to_ids.items() if len(ids) > 1
    }
    if duplicate_names:
        for cat_name in sorted(duplicate_names.keys()):
            out.append(
                f"  {cat_name}: {duplicate_names[cat_name]} different category IDs"
            )
    else:
        out.append("  No duplicate category names found")
    out.append("")

    items_without_categories = [it for it in items if not (it.get("categories") or [])]
    if items_without_categories:
        out.append(f"Items without categories: {len(items_without_categories)}")
        for it in items_without_categories:
            out.append(f"  - {it.get('item_name','')}")
    else:
        out.append("Items without categories: 0")

    return "\n".join(out)
