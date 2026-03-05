"""Generate an aggressively deduped Adora LLM menu in Markdown (v9).

The output is designed for model prompt context (not API payload reconstruction):
- Supports both TakeOut and Delivery availability
- Name-only fields (no item/size/modifier IDs)
- Aggressive dedupe with shared group templates + shared modifier templates
- Delivery fields emitted only when different from TakeOut
- Group defaults omitted when zero/false
- Top-level modifier-weight rules

Usage:
    uv run python scripts/generate_menu_v9.py
    uv run python scripts/generate_menu_v9.py --input brenz_newalbany.json --output brenz_menu_v9.md
    uv run python scripts/generate_menu_v9.py --count-tokens
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from ._adora_name_qualifiers import build_qualified_name_maps

TAKEOUT_ORDER_TYPE_ID = 2
DELIVERY_ORDER_TYPE_ID = 3
SUPPORTED_ORDER_TYPES = ("TakeOut", "Delivery")
ORDER_TYPE_NAME_BY_ID = {
    TAKEOUT_ORDER_TYPE_ID: "TakeOut",
    DELIVERY_ORDER_TYPE_ID: "Delivery",
}
ORDER_TYPE_ID_BY_NAME = {
    name: order_type_id for order_type_id, name in ORDER_TYPE_NAME_BY_ID.items()
}
NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")

WEIGHT_LABEL_TO_CANONICAL = {
    "no": "no",
    "none": "no",
    "light": "light",
    "lite": "light",
    "regular": "regular",
    "reg": "regular",
    "extra": "extra",
    "double": "double",
    "triple": "triple",
}
WEIGHT_CANONICAL_ORDER = ["no", "light", "regular", "extra", "double", "triple"]
DEFAULT_WEIGHT_FALLBACK = ["No", "Light", "Regular", "Extra", "Double", "Triple"]


class WarningTracker:
    """Collect deterministic warning counts and a few human-readable examples."""

    def __init__(self, *, max_samples_per_code: int = 5) -> None:
        self._max_samples_per_code = max_samples_per_code
        self.counts: dict[str, int] = {}
        self.samples: dict[str, list[str]] = {}

    def warn(self, code: str, detail: str) -> None:
        """Record one warning event."""
        self.counts[code] = self.counts.get(code, 0) + 1
        sample_rows = self.samples.setdefault(code, [])
        if len(sample_rows) < self._max_samples_per_code and detail not in sample_rows:
            sample_rows.append(detail)

    def has_warnings(self) -> bool:
        """Return True when warnings were captured."""
        return bool(self.counts)

    def print_summary(self) -> None:
        """Print warning summary and representative samples to stderr."""
        if not self.counts:
            return

        print("\nWarnings:", file=sys.stderr)
        for code in sorted(self.counts):
            print(f"  - {code}: {self.counts[code]}", file=sys.stderr)
            for sample in self.samples.get(code, []):
                print(f"      - {sample}", file=sys.stderr)


def load_menu(path: Path) -> dict[str, Any]:
    """Load source Adora menu JSON."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object.")
    return data


def estimate_tokens(text: str) -> int:
    """Rough token estimate for rendered markdown."""
    return len(text) // 4


def _normalize_name(value: str) -> str:
    """Normalize user-visible text for deterministic sorting and lookups."""
    return NORMALIZATION_PATTERN.sub(" ", value.casefold()).strip()


def _clean_name(value: Any) -> str:
    """Trim and normalize whitespace for display names."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _stable_json(value: Any) -> str:
    """Return stable JSON for dedupe signatures."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _coerce_float(
    value: Any,
    *,
    default: float,
    warnings: WarningTracker,
    code: str,
    context: str,
) -> float:
    """Convert value to float, warning and falling back when invalid."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        warnings.warn(code, f"{context} value={value!r}; using default {default}")
        return default


def _coerce_int(
    value: Any,
    *,
    default: int,
    warnings: WarningTracker,
    code: str,
    context: str,
) -> int:
    """Convert value to int, warning and falling back when invalid."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        warnings.warn(code, f"{context} value={value!r}; using default {default}")
        return default


def _extract_modifier_weight_rules(raw_menu: dict[str, Any]) -> dict[str, Any]:
    """Build top-level modifier-weight guidance from store labels."""
    label_by_canonical: dict[str, str] = {}
    other_labels: list[str] = []
    default_label: str | None = None

    raw_weights = raw_menu.get("modifier_weights", [])
    if not isinstance(raw_weights, list):
        raw_weights = []

    for row in raw_weights:
        if not isinstance(row, dict):
            continue
        label = _clean_name(row.get("name"))
        if not label:
            continue

        canonical = WEIGHT_LABEL_TO_CANONICAL.get(_normalize_name(label))
        if canonical:
            # Keep first observed label for each canonical slot to avoid duplicates.
            label_by_canonical.setdefault(canonical, label)
        elif label not in other_labels:
            other_labels.append(label)

        if row.get("default", False) and default_label is None:
            default_label = label

    ordered_labels = [
        label_by_canonical[key]
        for key in WEIGHT_CANONICAL_ORDER
        if key in label_by_canonical
    ]
    if not ordered_labels:
        ordered_labels = list(DEFAULT_WEIGHT_FALLBACK)
    ordered_labels.extend(
        sorted(
            [label for label in other_labels if label not in ordered_labels],
            key=_normalize_name,
        )
    )

    no_label = label_by_canonical.get("no")
    non_default_allowed = [label for label in ordered_labels if label != no_label]
    if no_label is None:
        non_default_allowed = [
            label for label in ordered_labels if _normalize_name(label) != "no"
        ]

    if default_label is None:
        default_label = label_by_canonical.get("regular", "Regular")

    return {
        "default_weight": default_label,
        "default_modifier_allowed": ordered_labels,
        "non_default_modifier_allowed": non_default_allowed,
    }


def _build_name_lookups(
    raw_menu: dict[str, Any],
    warnings: WarningTracker,
) -> tuple[dict[int, str], dict[int, str], dict[int, dict[str, Any]]]:
    """Build common lookup maps from raw menu payload."""
    size_name_by_id: dict[int, str] = {}
    raw_sizes = raw_menu.get("sizes", [])
    if not isinstance(raw_sizes, list):
        warnings.warn(
            "invalid_sizes_shape", "Top-level sizes is not a list; treating as empty."
        )
        raw_sizes = []
    for size in raw_sizes:
        if not isinstance(size, dict):
            continue
        size_id = size.get("size_id")
        size_name = _clean_name(size.get("name"))
        if isinstance(size_id, int) and size_name:
            size_name_by_id[size_id] = size_name

    modifier_name_by_id: dict[int, str] = {}
    raw_modifiers = raw_menu.get("modifiers", [])
    if not isinstance(raw_modifiers, list):
        warnings.warn(
            "invalid_modifiers_shape",
            "Top-level modifiers is not a list; treating as empty.",
        )
        raw_modifiers = []
    for modifier in raw_modifiers:
        if not isinstance(modifier, dict):
            continue
        modifier_id = modifier.get("modifier_id")
        modifier_name = _clean_name(modifier.get("name"))
        if isinstance(modifier_id, int) and modifier_name:
            modifier_name_by_id[modifier_id] = modifier_name

    top_group_by_id: dict[int, dict[str, Any]] = {}
    raw_groups = raw_menu.get("modifier_groups", [])
    if not isinstance(raw_groups, list):
        warnings.warn(
            "invalid_top_modifier_groups_shape",
            "Top-level modifier_groups is not a list; treating as empty.",
        )
        raw_groups = []
    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        group_id = group.get("modifier_group_id")
        if isinstance(group_id, int):
            top_group_by_id[group_id] = group

    return size_name_by_id, modifier_name_by_id, top_group_by_id


def _extract_order_type_metadata(
    raw_menu: dict[str, Any],
    warnings: WarningTracker,
) -> dict[str, dict[str, Any]]:
    """Extract order-type metadata with deterministic defaults for known order types."""
    metadata: dict[str, dict[str, Any]] = {
        "TakeOut": {
            "available": False,
            "order_type_id": TAKEOUT_ORDER_TYPE_ID,
            "name": "TakeOut",
            "address_required": False,
            "minimum_amount": 0.0,
            "charge": 0.0,
            "wait_time": 0,
        },
        "Delivery": {
            "available": False,
            "order_type_id": DELIVERY_ORDER_TYPE_ID,
            "name": "Delivery",
            "address_required": True,
            "minimum_amount": 0.0,
            "charge": 0.0,
            "wait_time": 0,
        },
    }

    raw_order_types = raw_menu.get("order_types", [])
    if not isinstance(raw_order_types, list):
        warnings.warn(
            "invalid_order_types_shape",
            "Top-level order_types is not a list; using defaults.",
        )
        return metadata

    for row in raw_order_types:
        if not isinstance(row, dict):
            continue

        order_type_id = row.get("order_type_id")
        if not isinstance(order_type_id, int):
            continue

        order_type_name = ORDER_TYPE_NAME_BY_ID.get(order_type_id)
        if order_type_name is None:
            warnings.warn(
                "unknown_order_type_id",
                f"Top-level order_types contains unsupported order_type_id={order_type_id}",
            )
            continue

        entry = metadata[order_type_name]
        entry["available"] = True

        display_name = _clean_name(row.get("name"))
        if display_name:
            entry["name"] = display_name

        entry["address_required"] = bool(
            row.get("address_required", entry["address_required"])
        )
        entry["minimum_amount"] = _coerce_float(
            row.get("minimum_amount"),
            default=entry["minimum_amount"],
            warnings=warnings,
            code="invalid_order_type_number",
            context=f"order_types[{order_type_name}].minimum_amount",
        )
        entry["charge"] = _coerce_float(
            row.get("charge"),
            default=entry["charge"],
            warnings=warnings,
            code="invalid_order_type_number",
            context=f"order_types[{order_type_name}].charge",
        )
        entry["wait_time"] = _coerce_int(
            row.get("wait_time"),
            default=entry["wait_time"],
            warnings=warnings,
            code="invalid_order_type_number",
            context=f"order_types[{order_type_name}].wait_time",
        )

    return metadata


def _extract_prices_by_size(
    raw_prices: Any,
    size_name_by_id: dict[int, str],
    warnings: WarningTracker,
    *,
    error_code: str,
    context_prefix: str,
    exclude_zero_prices: bool = False,
) -> dict[str, float]:
    """Extract price-by-size mapping from raw price entries.

    Args:
        raw_prices: Raw prices list from Adora data (expected to be list of dicts)
        size_name_by_id: Mapping of size IDs to cleaned size names
        warnings: Warning tracker for validation issues
        error_code: Error code for price coercion warnings
        context_prefix: Context string for warnings (e.g., "Item 'Pizza'" or "Modifier 'Cheese'")
        exclude_zero_prices: If True, exclude prices <= 0 from result (default False)

    Returns:
        Dict mapping size names to prices
    """
    prices_by_size: dict[str, float] = {}

    if not isinstance(raw_prices, list):
        return prices_by_size

    for price_entry in raw_prices:
        if not isinstance(price_entry, dict):
            continue
        size_id = price_entry.get("size_id")
        if not isinstance(size_id, int):
            continue
        size_name = _clean_name(size_name_by_id.get(size_id))
        if not size_name:
            continue
        price = _coerce_float(
            price_entry.get("price"),
            default=0.0,
            warnings=warnings,
            code=error_code,
            context=f"{context_prefix} size '{size_name}' price",
        )
        if exclude_zero_prices and price <= 0:
            continue

        previous_price = prices_by_size.get(size_name)
        if previous_price is not None and previous_price != price:
            warnings.warn(
                "conflicting_size_price",
                (
                    f"{context_prefix} size '{size_name}' has conflicting prices "
                    f"{previous_price} and {price}; using latest."
                ),
            )
        prices_by_size[size_name] = price

    return prices_by_size


def _extract_sizes_by_order_type(
    item: dict[str, Any],
    size_name_by_id: dict[int, str],
    warnings: WarningTracker,
) -> tuple[dict[str, list[str]], dict[str, dict[str, bool]], dict[str, float]]:
    """Return per-order-type size names + per-size half-and-half allowance + prices."""
    item_name = _clean_name(item.get("name")) or "<unnamed item>"
    item_allows_half_half = bool(item.get("allow_halving", False))

    # Extract prices by size
    raw_prices = item.get("prices", [])
    if not isinstance(raw_prices, list):
        warnings.warn(
            "invalid_item_prices_shape",
            f"Item '{item_name}' has non-list prices; ignoring prices.",
        )
    size_prices = _extract_prices_by_size(
        raw_prices,
        size_name_by_id,
        warnings,
        error_code="invalid_price",
        context_prefix=f"Item '{item_name}'",
    )

    size_half_half_by_order_type: dict[str, dict[str, bool]] = {
        order_type: {} for order_type in SUPPORTED_ORDER_TYPES
    }

    order_types_value = item.get("order_types", [])
    if not isinstance(order_types_value, list):
        warnings.warn(
            "invalid_item_order_types_shape",
            f"Item '{item_name}' has non-list order_types; skipping order-type sizes.",
        )
        order_types_value = []

    for order_type in order_types_value:
        if not isinstance(order_type, dict):
            continue

        order_type_id = order_type.get("order_type_id")
        if not isinstance(order_type_id, int):
            continue

        order_type_name = ORDER_TYPE_NAME_BY_ID.get(order_type_id)
        if order_type_name is None:
            warnings.warn(
                "unknown_order_type_id",
                f"Item '{item_name}' has unsupported order_type_id={order_type_id}",
            )
            continue

        raw_sizes = order_type.get("sizes", [])
        if not isinstance(raw_sizes, list):
            warnings.warn(
                "invalid_order_type_sizes_shape",
                f"Item '{item_name}' {order_type_name} sizes is not a list; skipping.",
            )
            continue

        by_size_name = size_half_half_by_order_type[order_type_name]
        for size_entry in raw_sizes:
            if not isinstance(size_entry, dict):
                continue

            size_id = size_entry.get("size_id")
            if not isinstance(size_id, int):
                warnings.warn(
                    "invalid_size_id",
                    (
                        f"Item '{item_name}' {order_type_name} has invalid size_id="
                        f"{size_entry.get('size_id')!r}; skipping."
                    ),
                )
                continue

            size_name = _clean_name(size_name_by_id.get(size_id))
            if not size_name:
                warnings.warn(
                    "unknown_size_id",
                    f"Item '{item_name}' {order_type_name} references unknown size_id={size_id}",
                )
                continue

            allow_half_half = (
                bool(size_entry.get("allow_halving", False)) and item_allows_half_half
            )
            previous = by_size_name.get(size_name)
            if previous is not None and previous != allow_half_half:
                warnings.warn(
                    "conflicting_size_half_half",
                    (
                        f"Item '{item_name}' {order_type_name} size '{size_name}' has conflicting "
                        "allow_halving; using false."
                    ),
                )
                by_size_name[size_name] = False
                continue

            if previous is None:
                by_size_name[size_name] = allow_half_half
            else:
                # Preserve conservative behavior if duplicates disagree in future passes.
                by_size_name[size_name] = previous and allow_half_half

    sizes_by_order_type = {
        order_type: sorted(size_map)
        for order_type, size_map in size_half_half_by_order_type.items()
    }
    ordered_half_half = {
        order_type: {
            size_name: size_half_half_by_order_type[order_type][size_name]
            for size_name in sizes_by_order_type[order_type]
        }
        for order_type in SUPPORTED_ORDER_TYPES
    }

    return sizes_by_order_type, ordered_half_half, size_prices


def _pick_group_constraints(
    item_group: dict[str, Any], top_group: dict[str, Any] | None
) -> tuple[int, int, bool]:
    """Merge useful per-group constraints with item-level precedence."""
    top_group = top_group or {}

    item_min = int(item_group.get("min_required_modifier", 0) or 0)
    top_min = int(top_group.get("min_required_modifier", 0) or 0)
    min_required = item_min if item_min > 0 else top_min

    item_max = int(item_group.get("max_allowed_modifier", 0) or 0)
    top_max = int(top_group.get("max_allowed_modifier", 0) or 0)
    max_allowed = item_max if item_max > 0 else top_max

    must_toggle = bool(
        item_group.get("must_toggle", False) or top_group.get("must_toggle", False)
    )
    return min_required, max_allowed, must_toggle


def _extract_item_groups(
    item: dict[str, Any],
    modifier_name_by_id: dict[int, str],
    modifier_occurrence_name_by_key: dict[tuple[int, int, int], str],
    top_group_by_id: dict[int, dict[str, Any]],
    size_name_by_id: dict[int, str],
    warnings: WarningTracker,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build name-only group rows and item-level default modifier names."""
    group_rows: list[dict[str, Any]] = []
    item_default_modifiers: set[str] = set()

    item_name = _clean_name(item.get("name")) or "<unnamed item>"
    item_id = item.get("item_id")
    raw_groups = item.get("modifier_groups", [])
    if not isinstance(raw_groups, list):
        warnings.warn(
            "invalid_item_modifier_groups_shape",
            f"Item '{item_name}' has non-list modifier_groups; ignoring groups.",
        )
        raw_groups = []

    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        group_id = group.get("modifier_group_id")
        if not isinstance(group_id, int):
            continue

        top_group = top_group_by_id.get(group_id, {})
        group_name = _clean_name(group.get("name")) or _clean_name(
            top_group.get("name")
        )
        if not group_name:
            group_name = f"Group {group_id}"

        min_required, max_allowed, must_toggle = _pick_group_constraints(
            group, top_group
        )
        supports_half_half = bool(group.get("allow_halving", False))

        allowed_modifiers: set[str] = set()
        raw_group_modifiers = group.get("modifiers", [])
        if not isinstance(raw_group_modifiers, list):
            warnings.warn(
                "invalid_group_modifiers_shape",
                f"Item '{item_name}' group '{group_name}' modifiers is not a list; ignoring group.",
            )
            raw_group_modifiers = []

        # Extract modifier names, defaults, and prices
        modifier_prices: dict[str, dict[str, float]] = {}

        for modifier in raw_group_modifiers:
            if not isinstance(modifier, dict):
                continue
            modifier_id = modifier.get("modifier_id")
            if not isinstance(modifier_id, int):
                continue
            modifier_name = ""
            if isinstance(item_id, int):
                modifier_name = _clean_name(
                    modifier_occurrence_name_by_key.get(
                        (item_id, group_id, modifier_id), ""
                    )
                )
            if not modifier_name:
                modifier_name = _clean_name(modifier_name_by_id.get(modifier_id))
            if not modifier_name:
                continue
            allowed_modifiers.add(modifier_name)
            if bool(modifier.get("default", False)):
                item_default_modifiers.add(modifier_name)

            # Extract modifier prices (per size) - only include prices > 0
            raw_modifier_price = modifier.get("price", [])
            if not isinstance(raw_modifier_price, list):
                warnings.warn(
                    "invalid_modifier_price",
                    f"Modifier '{modifier_name}' has non-list price data; expected list",
                )
                prices_by_size = {}
            else:
                prices_by_size = _extract_prices_by_size(
                    raw_modifier_price,
                    size_name_by_id,
                    warnings,
                    error_code="invalid_modifier_price",
                    context_prefix=f"Modifier '{modifier_name}'",
                    exclude_zero_prices=True,
                )
            if prices_by_size:
                # Check for duplicate modifier names and merge prices
                if modifier_name in modifier_prices:
                    existing_prices = modifier_prices[modifier_name]
                    for size_name, new_price in prices_by_size.items():
                        if size_name in existing_prices:
                            existing_price = existing_prices[size_name]
                            if existing_price != new_price:
                                warnings.warn(
                                    "duplicate_modifier_price_conflict",
                                    (
                                        f"Modifier '{modifier_name}' has conflicting prices for "
                                        f"size '{size_name}': {existing_price} and {new_price}; "
                                        f"using latest."
                                    ),
                                )
                                existing_prices[size_name] = new_price
                        else:
                            existing_prices[size_name] = new_price
                else:
                    modifier_prices[modifier_name] = prices_by_size

        sorted_allowed = sorted(allowed_modifiers, key=_normalize_name)
        if not sorted_allowed:
            continue

        group_data = {
            "name": group_name,
            "supports_half_half": supports_half_half,
            "min_required": min_required,
            "max_allowed": max_allowed,
            "must_toggle": must_toggle,
            "allowed_modifiers": sorted_allowed,
        }

        # Include modifier prices if any were found
        if modifier_prices:
            group_data["modifier_prices"] = modifier_prices

        group_rows.append(group_data)

    group_rows.sort(key=lambda row: _normalize_name(row["name"]))
    return group_rows, sorted(item_default_modifiers, key=_normalize_name)


def _to_group_template_row(group: dict[str, Any]) -> dict[str, Any]:
    """Build compact group template row, omitting default-valued fields."""
    row = {
        "name": group["name"],
        "allowed_modifiers": group["allowed_modifiers"],
    }

    min_required = int(group.get("min_required", 0) or 0)
    if min_required > 0:
        row["min_required"] = min_required

    max_allowed = int(group.get("max_allowed", 0) or 0)
    if max_allowed > 0:
        row["max_allowed"] = max_allowed

    if bool(group.get("must_toggle", False)):
        row["must_toggle"] = True

    # Include modifier prices if present
    modifier_prices = group.get("modifier_prices")
    if modifier_prices:
        row["modifier_prices"] = modifier_prices

    return row


def _normalize_modifier_template(
    template: dict[str, Any],
    *,
    group_id_by_signature: dict[str, str],
    group_templates: dict[str, dict[str, Any]],
    modifier_price_id_by_signature: dict[str, str],
    modifier_price_templates: dict[str, dict[str, dict[str, float]]],
) -> dict[str, Any]:
    """Convert one full template into compact group refs + non-halvable refs."""
    group_refs: list[str] = []
    non_halvable_group_refs: list[str] = []

    for group in template.get("groups", []):
        # Create compact version WITH modifier_prices initially (needed for signature)
        compact_group = _to_group_template_row(group)

        # Deduplicate modifier prices BEFORE computing group signature
        modifier_prices = compact_group.pop("modifier_prices", None)
        if modifier_prices:
            mod_price_signature = _stable_json(modifier_prices)
            mod_price_id = modifier_price_id_by_signature.get(mod_price_signature)
            if mod_price_id is None:
                mod_price_id = f"mprc_{len(modifier_price_id_by_signature) + 1:03d}"
                modifier_price_id_by_signature[mod_price_signature] = mod_price_id
                modifier_price_templates[mod_price_id] = modifier_prices
            compact_group["modifier_price_ref"] = mod_price_id

        # NOW compute group signature (includes modifier_price_ref if present)
        group_signature = _stable_json(compact_group)
        group_id = group_id_by_signature.get(group_signature)

        if group_id is None:
            group_id = f"grp_{len(group_id_by_signature) + 1:03d}"
            group_id_by_signature[group_signature] = group_id
            group_templates[group_id] = compact_group

        group_refs.append(group_id)
        if not bool(group.get("supports_half_half", False)):
            non_halvable_group_refs.append(group_id)

    template_row: dict[str, Any] = {"group_refs": group_refs}
    if non_halvable_group_refs:
        template_row["non_halvable_group_refs"] = non_halvable_group_refs
    return template_row


def build_llm_menu_v9(
    raw_menu: dict[str, Any],
    *,
    warnings: WarningTracker | None = None,
) -> dict[str, Any]:
    """Build aggressively deduped name-only menu for LLM prompt context."""
    warnings = warnings or WarningTracker()
    qualified_names = build_qualified_name_maps(raw_menu)

    size_name_by_id, modifier_name_by_id, top_group_by_id = _build_name_lookups(
        raw_menu, warnings
    )
    order_type_metadata = _extract_order_type_metadata(raw_menu, warnings)
    modifier_weights = _extract_modifier_weight_rules(raw_menu)

    sizes_by_order_type_set: dict[str, set[str]] = {
        order_type: set() for order_type in SUPPORTED_ORDER_TYPES
    }
    template_by_signature: dict[str, dict[str, Any]] = {}
    item_rows: list[dict[str, Any]] = []

    raw_items = raw_menu.get("items", [])
    if not isinstance(raw_items, list):
        warnings.warn(
            "invalid_items_shape", "Top-level items is not a list; treating as empty."
        )
        raw_items = []

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue

        item_name = ""
        item_id = raw_item.get("item_id")
        if isinstance(item_id, int):
            item_name = _clean_name(qualified_names.item_label_by_id.get(item_id, ""))
        if not item_name:
            item_name = _clean_name(raw_item.get("name"))
        if not item_name:
            warnings.warn(
                "invalid_item_name", "Skipped one item with missing/empty name."
            )
            continue

        (
            sizes_by_order_type,
            size_half_half_by_order_type,
            size_prices,
        ) = _extract_sizes_by_order_type(raw_item, size_name_by_id, warnings)
        if not any(
            sizes_by_order_type[order_type] for order_type in SUPPORTED_ORDER_TYPES
        ):
            continue

        group_rows, item_defaults = _extract_item_groups(
            raw_item,
            modifier_name_by_id=modifier_name_by_id,
            modifier_occurrence_name_by_key=qualified_names.modifier_occurrence_label,
            top_group_by_id=top_group_by_id,
            size_name_by_id=size_name_by_id,
            warnings=warnings,
        )

        template_body = {"groups": group_rows}
        template_signature = _stable_json(template_body)
        template_by_signature.setdefault(template_signature, template_body)

        for order_type in SUPPORTED_ORDER_TYPES:
            sizes_by_order_type_set[order_type].update(sizes_by_order_type[order_type])

        item_rows.append(
            {
                "_template_signature": template_signature,
                "name": item_name,
                "sizes_by_order_type": sizes_by_order_type,
                "size_half_half_by_order_type": size_half_half_by_order_type,
                "size_prices": size_prices,
                "default_modifiers": item_defaults,
            }
        )

    template_signatures = sorted(template_by_signature)
    template_id_by_signature = {
        signature: f"tpl_{index + 1:03d}"
        for index, signature in enumerate(template_signatures)
    }

    group_id_by_signature: dict[str, str] = {}
    group_templates: dict[str, dict[str, Any]] = {}
    modifier_price_id_by_signature: dict[str, str] = {}
    modifier_price_templates: dict[str, dict[str, dict[str, float]]] = {}
    modifier_templates: dict[str, dict[str, Any]] = {}
    for signature in template_signatures:
        template_id = template_id_by_signature[signature]
        modifier_templates[template_id] = _normalize_modifier_template(
            template_by_signature[signature],
            group_id_by_signature=group_id_by_signature,
            group_templates=group_templates,
            modifier_price_id_by_signature=modifier_price_id_by_signature,
            modifier_price_templates=modifier_price_templates,
        )

    # Deduplicate item prices into templates
    price_id_by_signature: dict[str, str] = {}
    price_templates: dict[str, dict[str, Any]] = {}

    items: list[dict[str, Any]] = []
    for row in sorted(item_rows, key=lambda item: _normalize_name(item["name"])):
        item_sizes_takeout = list(row["sizes_by_order_type"]["TakeOut"])
        item_sizes_delivery = list(row["sizes_by_order_type"]["Delivery"])
        item_half_half_takeout = dict(row["size_half_half_by_order_type"]["TakeOut"])
        item_half_half_delivery = dict(row["size_half_half_by_order_type"]["Delivery"])
        item_prices = row["size_prices"]

        # Build size_prices dict ordered by takeout and delivery sizes
        ordered_takeout_prices = {
            size_name: item_prices[size_name]
            for size_name in item_sizes_takeout
            if size_name in item_prices
        }
        ordered_delivery_prices = {
            size_name: item_prices[size_name]
            for size_name in item_sizes_delivery
            if size_name in item_prices
        }

        # Deduplicate prices into templates
        price_template: dict[str, Any]
        if (
            item_sizes_delivery != item_sizes_takeout
            and ordered_delivery_prices != ordered_takeout_prices
        ):
            # Different prices for takeout vs delivery
            price_template = {}
            if ordered_takeout_prices:
                price_template["takeout"] = ordered_takeout_prices
            if ordered_delivery_prices:
                price_template["delivery"] = ordered_delivery_prices
        else:
            # Same prices for both order types - store directly without nesting
            price_template = ordered_takeout_prices

        price_ref = None
        if price_template:
            price_signature = _stable_json(price_template)
            price_ref = price_id_by_signature.get(price_signature)
            if price_ref is None:
                price_ref = f"prc_{len(price_id_by_signature) + 1:03d}"
                price_id_by_signature[price_signature] = price_ref
                price_templates[price_ref] = price_template

        item_data: dict[str, Any] = {
            "name": row["name"],
            "sizes": item_sizes_takeout,
            "size_half_half": item_half_half_takeout,
            "template": template_id_by_signature[row["_template_signature"]],
        }

        if price_ref:
            item_data["price_ref"] = price_ref

        if item_sizes_delivery != item_sizes_takeout:
            item_data["delivery_sizes"] = item_sizes_delivery
        if item_half_half_delivery != item_half_half_takeout:
            item_data["delivery_size_half_half"] = item_half_half_delivery
        if row["default_modifiers"]:
            item_data["default_modifiers"] = row["default_modifiers"]

        items.append(item_data)

    top_sizes_by_order_type = {
        order_type: sorted(sizes_by_order_type_set[order_type], key=_normalize_name)
        for order_type in SUPPORTED_ORDER_TYPES
    }
    top_sizes_takeout = top_sizes_by_order_type["TakeOut"]
    top_sizes_delivery = top_sizes_by_order_type["Delivery"]

    result: dict[str, Any] = {
        "version": "adora_llm_menu_v9",
        "order_type": "TakeOut",
        "order_types": order_type_metadata,
        "tool_rules": {
            "replace_same_group_only": True,
            "non_default_cannot_use_no": True,
            "sides_allowed": [1, 2],
            "delivery_fallback_to_takeout": True,
        },
        "sizes": top_sizes_takeout,
        "modifier_weights": modifier_weights,
        "price_templates": price_templates,
        "modifier_price_templates": modifier_price_templates,
        "group_templates": group_templates,
        "modifier_templates": modifier_templates,
        "items": items,
    }
    if top_sizes_delivery != top_sizes_takeout:
        result["delivery_sizes"] = top_sizes_delivery

    return result


def _iter_dict_keys(value: Any) -> list[str]:
    """Collect all dict keys recursively for schema hygiene checks."""
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_iter_dict_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_iter_dict_keys(child))
    return keys


def verify_llm_menu_v9(menu_model: dict[str, Any]) -> None:
    """Run structural checks for correctness and compact-schema hygiene."""
    required_top_level = [
        "version",
        "order_type",
        "order_types",
        "tool_rules",
        "sizes",
        "modifier_weights",
        "price_templates",
        "modifier_price_templates",
        "group_templates",
        "modifier_templates",
        "items",
    ]
    for key in required_top_level:
        if key not in menu_model:
            raise ValueError(f"Missing required top-level key: {key}")

    if menu_model["version"] != "adora_llm_menu_v9":
        raise ValueError("version must be adora_llm_menu_v9")

    if menu_model["order_type"] != "TakeOut":
        raise ValueError("order_type must be TakeOut")

    all_keys = _iter_dict_keys(menu_model)
    id_like_keys = [
        key
        for key in all_keys
        if (key.casefold() == "id" or key.casefold().endswith("_id"))
        and key != "order_type_id"
    ]
    if id_like_keys:
        raise ValueError(
            f"Output must not contain id keys, found: {sorted(set(id_like_keys))}"
        )

    order_types = menu_model.get("order_types", {})
    if not isinstance(order_types, dict):
        raise ValueError("order_types must be an object")

    for order_type in SUPPORTED_ORDER_TYPES:
        entry = order_types.get(order_type)
        if not isinstance(entry, dict):
            raise ValueError(f"order_types.{order_type} must be an object")

        required_entry_keys = {
            "available",
            "order_type_id",
            "name",
            "address_required",
            "minimum_amount",
            "charge",
            "wait_time",
        }
        missing_entry_keys = required_entry_keys - set(entry)
        if missing_entry_keys:
            raise ValueError(
                f"order_types.{order_type} missing required keys: {sorted(missing_entry_keys)}"
            )

        if entry.get("order_type_id") != ORDER_TYPE_ID_BY_NAME[order_type]:
            raise ValueError(
                f"order_types.{order_type}.order_type_id must be "
                f"{ORDER_TYPE_ID_BY_NAME[order_type]}"
            )

        if not isinstance(entry.get("available"), bool):
            raise ValueError(f"order_types.{order_type}.available must be a boolean")
        if not isinstance(entry.get("name"), str) or not entry["name"].strip():
            raise ValueError(f"order_types.{order_type}.name must be non-empty string")
        if not isinstance(entry.get("address_required"), bool):
            raise ValueError(
                f"order_types.{order_type}.address_required must be a boolean"
            )
        if not isinstance(entry.get("minimum_amount"), (int, float)):
            raise ValueError(f"order_types.{order_type}.minimum_amount must be numeric")
        if not isinstance(entry.get("charge"), (int, float)):
            raise ValueError(f"order_types.{order_type}.charge must be numeric")
        if not isinstance(entry.get("wait_time"), int):
            raise ValueError(f"order_types.{order_type}.wait_time must be an integer")

    top_sizes_takeout = menu_model.get("sizes")
    top_sizes_delivery = menu_model.get("delivery_sizes")
    price_templates = menu_model.get("price_templates", {})
    modifier_price_templates = menu_model.get("modifier_price_templates", {})
    group_templates = menu_model.get("group_templates", {})
    modifier_templates = menu_model.get("modifier_templates", {})
    items = menu_model.get("items", [])

    if not isinstance(top_sizes_takeout, list):
        raise ValueError("sizes must be a list")
    if top_sizes_delivery is not None and not isinstance(top_sizes_delivery, list):
        raise ValueError("delivery_sizes must be a list when present")
    if not isinstance(price_templates, dict):
        raise ValueError("price_templates must be an object")
    if not isinstance(modifier_price_templates, dict):
        raise ValueError("modifier_price_templates must be an object")
    if not isinstance(group_templates, dict):
        raise ValueError("group_templates must be an object")
    if not isinstance(modifier_templates, dict):
        raise ValueError("modifier_templates must be an object")
    if not isinstance(items, list):
        raise ValueError("items must be a list")

    top_takeout_size_set = set(top_sizes_takeout)
    top_delivery_size_set = (
        set(top_sizes_delivery)
        if top_sizes_delivery is not None
        else set(top_sizes_takeout)
    )

    # Validate price_templates
    for price_id, price_data in price_templates.items():
        if not isinstance(price_data, dict):
            raise ValueError(f"price_templates.{price_id} must be an object")

        # Check if this is direct format (no takeout/delivery keys) or nested format
        has_takeout = "takeout" in price_data
        has_delivery = "delivery" in price_data

        if has_takeout or has_delivery:
            # Nested format with takeout/delivery keys
            takeout_prices = price_data.get("takeout")
            if takeout_prices is not None:
                if not isinstance(takeout_prices, dict):
                    raise ValueError(
                        f"price_templates.{price_id}.takeout must be an object"
                    )
                for size_name, price in takeout_prices.items():
                    if not isinstance(price, (int, float)) or isinstance(price, bool):
                        raise ValueError(
                            f"price_templates.{price_id}.takeout['{size_name}'] must be numeric"
                        )
                    if price < 0:
                        raise ValueError(
                            f"price_templates.{price_id}.takeout['{size_name}'] must be >= 0"
                        )

            delivery_prices = price_data.get("delivery")
            if delivery_prices is not None:
                if not isinstance(delivery_prices, dict):
                    raise ValueError(
                        f"price_templates.{price_id}.delivery must be an object"
                    )
                for size_name, price in delivery_prices.items():
                    if not isinstance(price, (int, float)) or isinstance(price, bool):
                        raise ValueError(
                            f"price_templates.{price_id}.delivery['{size_name}'] must be numeric"
                        )
                    if price < 0:
                        raise ValueError(
                            f"price_templates.{price_id}.delivery['{size_name}'] must be >= 0"
                        )
        else:
            # Direct format - prices stored directly without nesting
            for size_name, price in price_data.items():
                if not isinstance(price, (int, float)) or isinstance(price, bool):
                    raise ValueError(
                        f"price_templates.{price_id}['{size_name}'] must be numeric"
                    )
                if price < 0:
                    raise ValueError(
                        f"price_templates.{price_id}['{size_name}'] must be >= 0"
                    )

    # Validate modifier_price_templates
    for mod_price_id, mod_price_map in modifier_price_templates.items():
        if not isinstance(mod_price_map, dict):
            raise ValueError(
                f"modifier_price_templates.{mod_price_id} must be an object"
            )
        for mod_name, price_map in mod_price_map.items():
            if not isinstance(price_map, dict):
                raise ValueError(
                    f"modifier_price_templates.{mod_price_id}['{mod_name}'] must be an object"
                )
            for size_name, price in price_map.items():
                if not isinstance(price, (int, float)) or isinstance(price, bool):
                    raise ValueError(
                        f"modifier_price_templates.{mod_price_id}['{mod_name}']['{size_name}'] "
                        f"must be numeric"
                    )
                if price <= 0:
                    raise ValueError(
                        f"modifier_price_templates.{mod_price_id}['{mod_name}']['{size_name}'] "
                        f"must be > 0"
                    )

    for group_id, group in group_templates.items():
        if not isinstance(group, dict):
            raise ValueError(f"group_templates.{group_id} must be an object")
        if not isinstance(group.get("name"), str) or not group["name"].strip():
            raise ValueError(
                f"group_templates.{group_id}.name must be non-empty string"
            )
        allowed = group.get("allowed_modifiers")
        if not isinstance(allowed, list) or not allowed:
            raise ValueError(
                f"group_templates.{group_id}.allowed_modifiers must be non-empty list"
            )
        if "min_required" in group and (
            not isinstance(group["min_required"], int) or group["min_required"] < 0
        ):
            raise ValueError(
                f"group_templates.{group_id}.min_required must be non-negative integer"
            )
        if "max_allowed" in group and (
            not isinstance(group["max_allowed"], int) or group["max_allowed"] < 0
        ):
            raise ValueError(
                f"group_templates.{group_id}.max_allowed must be non-negative integer"
            )
        if "must_toggle" in group and not isinstance(group["must_toggle"], bool):
            raise ValueError(f"group_templates.{group_id}.must_toggle must be boolean")
        if "modifier_price_ref" in group:
            modifier_price_ref = group["modifier_price_ref"]
            if (
                not isinstance(modifier_price_ref, str)
                or modifier_price_ref not in modifier_price_templates
            ):
                raise ValueError(
                    f"group_templates.{group_id}.modifier_price_ref must reference "
                    "modifier_price_templates"
                )

    for template_id, template in modifier_templates.items():
        if not isinstance(template, dict):
            raise ValueError(f"modifier_templates.{template_id} must be an object")

        group_refs = template.get("group_refs")
        if not isinstance(group_refs, list):
            raise ValueError(
                f"modifier_templates.{template_id}.group_refs must be a list"
            )
        for group_id in group_refs:
            if group_id not in group_templates:
                raise ValueError(
                    f"modifier_templates.{template_id} references unknown group '{group_id}'"
                )

        non_halvable_refs = template.get("non_halvable_group_refs", [])
        if not isinstance(non_halvable_refs, list):
            raise ValueError(
                f"modifier_templates.{template_id}.non_halvable_group_refs must be a list"
            )
        invalid_refs = sorted(set(non_halvable_refs) - set(group_refs))
        if invalid_refs:
            raise ValueError(
                f"modifier_templates.{template_id} non-halvable refs not in group_refs: "
                f"{invalid_refs}"
            )

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each item row must be an object")

        item_name = item.get("name", "")
        template_id = item.get("template")
        if not isinstance(template_id, str) or template_id not in modifier_templates:
            raise ValueError(
                f"Item '{item_name}' references unknown template '{template_id}'"
            )

        # Validate price_ref if present
        price_ref = item.get("price_ref")
        if price_ref is not None:
            if not isinstance(price_ref, str) or price_ref not in price_templates:
                raise ValueError(
                    f"Item '{item_name}' references unknown price_ref '{price_ref}'"
                )

        item_sizes_takeout = item.get("sizes")
        if not isinstance(item_sizes_takeout, list):
            raise ValueError(f"Item '{item_name}' sizes must be a list")
        if not set(item_sizes_takeout).issubset(top_takeout_size_set):
            raise ValueError(
                f"Item '{item_name}' includes TakeOut sizes not present in top-level sizes"
            )

        item_half_half_takeout = item.get("size_half_half")
        if not isinstance(item_half_half_takeout, dict):
            raise ValueError(f"Item '{item_name}' size_half_half must be an object")
        if set(item_half_half_takeout.keys()) != set(item_sizes_takeout):
            raise ValueError(
                f"Item '{item_name}' size_half_half keys must match sizes exactly"
            )

        item_sizes_delivery = item.get("delivery_sizes", item_sizes_takeout)
        if not isinstance(item_sizes_delivery, list):
            raise ValueError(
                f"Item '{item_name}' delivery_sizes must be a list when present"
            )
        if not set(item_sizes_delivery).issubset(top_delivery_size_set):
            raise ValueError(
                f"Item '{item_name}' includes Delivery sizes not present in "
                "top-level delivery sizes"
            )

        item_half_half_delivery = item.get(
            "delivery_size_half_half", item_half_half_takeout
        )
        if not isinstance(item_half_half_delivery, dict):
            raise ValueError(
                f"Item '{item_name}' delivery_size_half_half must be an object when present"
            )
        if set(item_half_half_delivery.keys()) != set(item_sizes_delivery):
            raise ValueError(
                f"Item '{item_name}' delivery_size_half_half keys must match delivery sizes exactly"
            )

        template = modifier_templates[template_id]
        allowed_modifiers = {
            modifier_name
            for group_id in template.get("group_refs", [])
            for modifier_name in group_templates.get(group_id, {}).get(
                "allowed_modifiers", []
            )
        }
        defaults = set(item.get("default_modifiers", []))
        if not defaults.issubset(allowed_modifiers):
            raise ValueError(
                f"Item '{item_name}' has default modifiers not allowed by template "
                f"'{template_id}': "
                f"{sorted(defaults - allowed_modifiers)}"
            )


def _yaml_scalar(value: Any) -> str:
    """Render a scalar YAML token using JSON-compatible escaping."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value, ensure_ascii=True)

    return json.dumps(str(value), ensure_ascii=True)


def _yaml_inline_list(value: list[Any], compact: bool) -> str | None:
    """Return inline YAML list when compact mode and all entries are scalar."""
    if not compact:
        return None
    if any(isinstance(entry, (dict, list)) for entry in value):
        return None
    return "[" + ", ".join(_yaml_scalar(entry) for entry in value) + "]"


def _yaml_dump_lines(value: Any, indent: int = 0, compact: bool = False) -> list[str]:
    """Serialize simple Python structures to deterministic YAML lines."""
    pad = " " * indent
    lines: list[str] = []

    if isinstance(value, dict):
        if not value:
            return [f"{pad}{{}}"]

        for key, item in value.items():
            safe_key = str(key)
            if isinstance(item, dict):
                if item:
                    lines.append(f"{pad}{safe_key}:")
                    lines.extend(
                        _yaml_dump_lines(item, indent=indent + 2, compact=compact)
                    )
                else:
                    lines.append(f"{pad}{safe_key}: {{}}")
                continue

            if isinstance(item, list):
                inline = _yaml_inline_list(item, compact=compact)
                if inline is not None:
                    lines.append(f"{pad}{safe_key}: {inline}")
                elif not item:
                    lines.append(f"{pad}{safe_key}: []")
                else:
                    lines.append(f"{pad}{safe_key}:")
                    lines.extend(
                        _yaml_dump_lines(item, indent=indent + 2, compact=compact)
                    )
                continue

            lines.append(f"{pad}{safe_key}: {_yaml_scalar(item)}")
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{pad}[]"]

        for item in value:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{pad}- {{}}")
                    continue
                lines.append(f"{pad}-")
                lines.extend(_yaml_dump_lines(item, indent=indent + 2, compact=compact))
                continue

            if isinstance(item, list):
                inline = _yaml_inline_list(item, compact=compact)
                if inline is not None:
                    lines.append(f"{pad}- {inline}")
                elif not item:
                    lines.append(f"{pad}- []")
                else:
                    lines.append(f"{pad}-")
                    lines.extend(
                        _yaml_dump_lines(item, indent=indent + 2, compact=compact)
                    )
                continue

            lines.append(f"{pad}- {_yaml_scalar(item)}")
        return lines

    return [f"{pad}{_yaml_scalar(value)}"]


def render_markdown(menu_model: dict[str, Any], compact: bool = False) -> str:
    """Render menu model as markdown with one fenced YAML block."""
    yaml_body = "\n".join(_yaml_dump_lines(menu_model, compact=compact)).rstrip()
    return "\n".join(
        [
            "# Adora LLM Menu v9",
            "",
            "```yaml",
            yaml_body,
            "```",
            "",
        ]
    )


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Generate markdown LLM menu v9 (aggressively deduped + qualified names)."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("brenz_newalbany.json"),
        help="Raw Adora menu JSON input path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("brenz_menu_v9.md"),
        help="Markdown output path.",
    )
    parser.add_argument(
        "--no-compact",
        action="store_true",
        help="Disable compact inline YAML lists for scalar arrays.",
    )
    parser.add_argument(
        "--count-tokens",
        action="store_true",
        help="Print rough token estimate for rendered markdown.",
    )
    args = parser.parse_args()

    print(f"Loading menu from {args.input}...")
    raw_menu = load_menu(args.input)

    warning_tracker = WarningTracker()

    print("Building LLM menu v9 model...")
    model = build_llm_menu_v9(raw_menu, warnings=warning_tracker)

    print("Running verification checks...")
    verify_llm_menu_v9(model)

    print("Rendering markdown...")
    rendered = render_markdown(model, compact=not args.no_compact)

    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote markdown menu to {args.output}")

    if args.count_tokens:
        print(f"Approx token count: ~{estimate_tokens(rendered):,}")

    if warning_tracker.has_warnings():
        warning_tracker.print_summary()

    print("\nSummary:")
    print(f"  - takeout sizes: {len(model.get('sizes', []))}")
    print(
        f"  - delivery sizes: {len(model.get('delivery_sizes', model.get('sizes', [])))}"
    )
    print(f"  - price templates: {len(model.get('price_templates', {}))}")
    print(
        f"  - modifier price templates: {len(model.get('modifier_price_templates', {}))}"
    )
    print(f"  - group templates: {len(model.get('group_templates', {}))}")
    print(f"  - templates: {len(model.get('modifier_templates', {}))}")
    print(f"  - items: {len(model.get('items', []))}")


if __name__ == "__main__":
    main()
