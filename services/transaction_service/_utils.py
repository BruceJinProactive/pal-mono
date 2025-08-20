"""
Transaction Service Utilities

Utility functions for the transaction/order service including data processing
and helper functions for order management.
"""

from typing import Any, List, Optional


def reconstruct_order_items(order_items: Optional[List[Any]]) -> Optional[List[dict]]:
    """Extract essential fields from order items for clean database storage."""
    if not order_items:
        return None

    def get_field(obj, *field_names):
        """Get first available field from object or dict-like."""
        for field in field_names:
            if isinstance(obj, dict) and field in obj:
                return obj.get(field)
            if hasattr(obj, field):
                return getattr(obj, field)
        return None

    def extract_modifiers(modifiers):
        """Extract essential modifier fields."""
        if not modifiers:
            return None
        return [
            {
                "modifier_id": get_field(mod, "modifier_id", "id"),
                "modifier_name": get_field(mod, "modifier_name", "name"),
            }
            for mod in modifiers
            if get_field(mod, "modifier_id", "id")
        ]

    result = []
    for item in order_items:
        item_id = get_field(item, "item_id", "id")
        if not item_id:
            continue

        quantity = get_field(item, "quantity", "qty")
        if quantity is None:
            quantity = 1

        reconstructed = {
            "item_id": item_id,
            "item_name": get_field(item, "item_name", "name"),
            "quantity": quantity,
        }

        modifiers = extract_modifiers(get_field(item, "modifiers", "mods"))
        if modifiers:
            reconstructed["modifiers"] = modifiers

        result.append(reconstructed)

    return result if result else None
