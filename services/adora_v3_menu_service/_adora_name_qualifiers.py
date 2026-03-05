"""Deterministic qualifier utilities for ambiguous Adora item/modifier names."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

TAKEOUT_ORDER_TYPE_ID = 2
NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_name(value: str) -> str:
    """Normalize user-facing text for deterministic matching."""
    return NORMALIZATION_PATTERN.sub(" ", value.casefold()).strip()


def clean_name(value: Any) -> str:
    """Trim and normalize internal whitespace in labels."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _append_qualifier(label: str, qualifier: str) -> str:
    """Append one readable qualifier block when present."""
    cleaned_qualifier = clean_name(qualifier)
    if not cleaned_qualifier:
        return label
    return f"{label} ({cleaned_qualifier})"


def _variant_letters(index: int) -> str:
    """Convert a zero-based index into Excel-like A/B/.../AA labels."""
    value = index + 1
    letters: list[str] = []
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _variant_label(index: int) -> str:
    """Return deterministic variant suffix label."""
    return f"Variant {_variant_letters(index)}"


def _sort_part(value: Any) -> tuple[int, Any, str]:
    """Build a deterministic sort part for mixed tuple keys."""
    if isinstance(value, int):
        return (0, value, str(value))
    cleaned = clean_name(value)
    return (1, normalize_name(cleaned), cleaned)


def _record_sort_key(record: dict[str, Any]) -> tuple[tuple[int, Any, str], ...]:
    """Build a stable sort key for collision tie-break groups."""
    key = record.get("key")
    if isinstance(key, tuple):
        return tuple(_sort_part(part) for part in key)
    return (_sort_part(key),)


def _choose_preferred_label(values: set[str]) -> str:
    """Choose one canonical label from a set of candidate values."""
    cleaned_values = {clean_name(value) for value in values}
    cleaned_values.discard("")
    if not cleaned_values:
        return ""
    return sorted(cleaned_values, key=lambda value: (normalize_name(value), value))[0]


def _collision_groups(
    records: list[dict[str, Any]],
    labels_by_key: dict[Any, str],
) -> list[list[dict[str, Any]]]:
    """Group records by current normalized label and return only collision groups."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = record["key"]
        grouped[normalize_name(labels_by_key[key])].append(record)
    return [rows for rows in grouped.values() if len(rows) > 1]


def _assign_qualified_labels(
    records: list[dict[str, Any]],
    *,
    qualifier_fields: list[str],
) -> dict[Any, str]:
    """Assign unique display labels using staged qualifiers + deterministic variants."""
    labels_by_key = {record["key"]: record["base_label"] for record in records}

    for field_name in qualifier_fields:
        for collision_rows in _collision_groups(records, labels_by_key):
            for record in collision_rows:
                qualifier = clean_name(record.get(field_name))
                if not qualifier:
                    continue
                key = record["key"]
                labels_by_key[key] = _append_qualifier(labels_by_key[key], qualifier)

    for collision_rows in _collision_groups(records, labels_by_key):
        for variant_index, record in enumerate(
            sorted(collision_rows, key=_record_sort_key)
        ):
            key = record["key"]
            labels_by_key[key] = _append_qualifier(
                labels_by_key[key],
                _variant_label(variant_index),
            )

    return labels_by_key


def _build_size_name_by_id(raw_menu: dict[str, Any]) -> dict[int, str]:
    """Build size_id -> display name lookup."""
    lookup: dict[int, str] = {}
    for size in raw_menu.get("sizes", []):
        if not isinstance(size, dict):
            continue
        size_id = size.get("size_id")
        if not isinstance(size_id, int):
            continue
        label = clean_name(size.get("name"))
        if label:
            lookup[size_id] = label
    return lookup


def _build_category_name_by_id(raw_menu: dict[str, Any]) -> dict[int, str]:
    """Build category_id -> display label lookup."""
    lookup: dict[int, str] = {}
    for category in raw_menu.get("categories", []):
        if not isinstance(category, dict):
            continue
        category_id = category.get("category_id")
        if not isinstance(category_id, int):
            continue
        label = clean_name(category.get("name"))
        if label:
            lookup[category_id] = label
    return lookup


def _build_web_category_name_by_id(raw_menu: dict[str, Any]) -> dict[int, str]:
    """Build web_category_id -> display label lookup."""
    lookup: dict[int, str] = {}
    for category in raw_menu.get("web_categories", []):
        if not isinstance(category, dict):
            continue
        category_id = category.get("web_category_id")
        if not isinstance(category_id, int):
            continue
        label = clean_name(category.get("name"))
        if label:
            lookup[category_id] = label
    return lookup


def _build_modifier_category_name_by_id(raw_menu: dict[str, Any]) -> dict[int, str]:
    """Build modifier_category_id -> display label lookup."""
    lookup: dict[int, str] = {}
    for category in raw_menu.get("modifier_categories", []):
        if not isinstance(category, dict):
            continue
        category_id = category.get("modifier_category_id")
        if not isinstance(category_id, int):
            continue
        label = clean_name(category.get("name"))
        if label and normalize_name(label) != "none":
            lookup[category_id] = label
    return lookup


def _build_top_group_name_by_id(raw_menu: dict[str, Any]) -> dict[int, str]:
    """Build modifier_group_id -> display label lookup from top-level groups."""
    lookup: dict[int, str] = {}
    for group in raw_menu.get("modifier_groups", []):
        if not isinstance(group, dict):
            continue
        group_id = group.get("modifier_group_id")
        if not isinstance(group_id, int):
            continue
        label = clean_name(group.get("name"))
        if label:
            lookup[group_id] = label
    return lookup


def _resolve_item_category_label(
    raw_item: dict[str, Any],
    *,
    category_name_by_id: dict[int, str],
    web_category_name_by_id: dict[int, str],
) -> str:
    """Resolve best available category label for one item."""
    web_category_id = raw_item.get("web_category_id")
    if isinstance(web_category_id, int):
        label = web_category_name_by_id.get(web_category_id) or category_name_by_id.get(
            web_category_id
        )
        if label:
            return label

    item_category_id = raw_item.get("item_category_id")
    if isinstance(item_category_id, int):
        return category_name_by_id.get(item_category_id, "")

    return ""


def _resolve_item_size_profile_label(
    raw_item: dict[str, Any],
    *,
    size_name_by_id: dict[int, str],
) -> str:
    """Build one human-readable TakeOut size profile label for an item."""
    size_names: set[str] = set()
    for order_type in raw_item.get("order_types", []):
        if not isinstance(order_type, dict):
            continue
        if order_type.get("order_type_id") != TAKEOUT_ORDER_TYPE_ID:
            continue
        for size_entry in order_type.get("sizes", []):
            if not isinstance(size_entry, dict):
                continue
            size_id = size_entry.get("size_id")
            if not isinstance(size_id, int):
                continue
            size_label = clean_name(size_name_by_id.get(size_id))
            if size_label:
                size_names.add(size_label)

    if not size_names:
        return ""
    ordered = sorted(size_names, key=lambda value: (normalize_name(value), value))
    return " / ".join(ordered)


def _description_option_label(base_name: str, description: Any) -> str:
    """Derive a useful disambiguation label from modifier description text."""
    cleaned_description = clean_name(description)
    if not cleaned_description:
        return ""

    cleaned_base_name = clean_name(base_name)
    if normalize_name(cleaned_description) == normalize_name(cleaned_base_name):
        return ""

    if cleaned_base_name:
        prefix_pattern = re.compile(
            rf"^{re.escape(cleaned_base_name)}[\s:\-]*", re.IGNORECASE
        )
        stripped = clean_name(prefix_pattern.sub("", cleaned_description))
        if stripped and normalize_name(stripped) != normalize_name(cleaned_description):
            return stripped

    return cleaned_description


def _resolve_group_label(
    raw_group: dict[str, Any],
    *,
    top_group_name_by_id: dict[int, str],
    group_id: int,
) -> str:
    """Resolve best group label from item-level then top-level metadata."""
    return (
        clean_name(raw_group.get("name"))
        or clean_name(top_group_name_by_id.get(group_id))
        or f"Group {group_id}"
    )


def _build_item_label_by_id(
    raw_menu: dict[str, Any],
    *,
    size_name_by_id: dict[int, str],
    category_name_by_id: dict[int, str],
    web_category_name_by_id: dict[int, str],
) -> dict[int, str]:
    """Build deterministic display labels for item IDs."""
    metadata_by_item_id: dict[int, dict[str, set[str]]] = defaultdict(
        lambda: {"base_names": set(), "category_labels": set(), "size_profiles": set()}
    )

    for raw_item in raw_menu.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        item_id = raw_item.get("item_id")
        if not isinstance(item_id, int):
            continue

        base_name = clean_name(raw_item.get("name"))
        if base_name:
            metadata_by_item_id[item_id]["base_names"].add(base_name)

        category_label = _resolve_item_category_label(
            raw_item,
            category_name_by_id=category_name_by_id,
            web_category_name_by_id=web_category_name_by_id,
        )
        if category_label:
            metadata_by_item_id[item_id]["category_labels"].add(category_label)

        size_profile = _resolve_item_size_profile_label(
            raw_item, size_name_by_id=size_name_by_id
        )
        if size_profile:
            metadata_by_item_id[item_id]["size_profiles"].add(size_profile)

    records: list[dict[str, Any]] = []
    for item_id in sorted(metadata_by_item_id):
        metadata = metadata_by_item_id[item_id]
        base_label = (
            _choose_preferred_label(metadata["base_names"]) or f"Item {item_id}"
        )
        records.append(
            {
                "key": item_id,
                "item_id": item_id,
                "base_label": base_label,
                "category_label": _choose_preferred_label(metadata["category_labels"]),
                "size_profile": _choose_preferred_label(metadata["size_profiles"]),
            }
        )

    records_by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_base[normalize_name(record["base_label"])].append(record)

    labels_by_id: dict[int, str] = {}
    for base_records in records_by_base.values():
        if len(base_records) == 1:
            record = base_records[0]
            labels_by_id[record["item_id"]] = record["base_label"]
            continue

        labels_by_key = _assign_qualified_labels(
            base_records,
            qualifier_fields=["category_label", "size_profile"],
        )
        for record in base_records:
            labels_by_id[record["item_id"]] = labels_by_key[record["key"]]

    return labels_by_id


def _build_modifier_labels(
    raw_menu: dict[str, Any],
    *,
    modifier_category_name_by_id: dict[int, str],
    top_group_name_by_id: dict[int, str],
) -> tuple[dict[tuple[int, int, int], str], dict[int, list[str]]]:
    """Build occurrence-level and global alias labels for modifiers."""
    metadata_by_modifier_id: dict[int, dict[str, set[str]]] = defaultdict(
        lambda: {
            "base_names": set(),
            "category_labels": set(),
            "description_labels": set(),
        }
    )

    for modifier in raw_menu.get("modifiers", []):
        if not isinstance(modifier, dict):
            continue
        modifier_id = modifier.get("modifier_id")
        if not isinstance(modifier_id, int):
            continue

        base_name = clean_name(modifier.get("name"))
        if base_name:
            metadata_by_modifier_id[modifier_id]["base_names"].add(base_name)

        modifier_category_id = modifier.get("modifier_category_id")
        if isinstance(modifier_category_id, int):
            category_label = clean_name(
                modifier_category_name_by_id.get(modifier_category_id)
            )
            if category_label:
                metadata_by_modifier_id[modifier_id]["category_labels"].add(
                    category_label
                )

        description_label = _description_option_label(
            base_name, modifier.get("description")
        )
        if description_label:
            metadata_by_modifier_id[modifier_id]["description_labels"].add(
                description_label
            )

    occurrence_group_label_by_key: dict[tuple[int, int, int], str] = {}
    occurrences_by_modifier_id: dict[int, list[tuple[int, int, int]]] = defaultdict(
        list
    )
    group_labels_by_modifier_id: dict[int, set[str]] = defaultdict(set)

    for raw_item in raw_menu.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        item_id = raw_item.get("item_id")
        if not isinstance(item_id, int):
            continue

        raw_groups = raw_item.get("modifier_groups", [])
        if not isinstance(raw_groups, list):
            continue

        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                continue
            group_id = raw_group.get("modifier_group_id")
            if not isinstance(group_id, int):
                continue

            group_label = _resolve_group_label(
                raw_group,
                top_group_name_by_id=top_group_name_by_id,
                group_id=group_id,
            )

            raw_group_modifiers = raw_group.get("modifiers", [])
            if not isinstance(raw_group_modifiers, list):
                continue

            for raw_group_modifier in raw_group_modifiers:
                if not isinstance(raw_group_modifier, dict):
                    continue
                modifier_id = raw_group_modifier.get("modifier_id")
                if not isinstance(modifier_id, int):
                    continue

                occurrence_key = (item_id, group_id, modifier_id)
                if occurrence_key not in occurrence_group_label_by_key:
                    occurrence_group_label_by_key[occurrence_key] = group_label
                    occurrences_by_modifier_id[modifier_id].append(occurrence_key)
                group_labels_by_modifier_id[modifier_id].add(group_label)

    modifier_ids = set(metadata_by_modifier_id) | set(occurrences_by_modifier_id)
    canonical_metadata_by_id: dict[int, dict[str, str]] = {}
    ids_by_base_name: dict[str, list[int]] = defaultdict(list)

    for modifier_id in sorted(modifier_ids):
        metadata = metadata_by_modifier_id[modifier_id]
        base_label = (
            _choose_preferred_label(metadata["base_names"]) or f"Modifier {modifier_id}"
        )
        category_label = _choose_preferred_label(metadata["category_labels"])
        description_label = _choose_preferred_label(metadata["description_labels"])
        canonical_metadata_by_id[modifier_id] = {
            "base_label": base_label,
            "category_label": category_label,
            "description_label": description_label,
        }
        ids_by_base_name[normalize_name(base_label)].append(modifier_id)

    occurrence_label_by_key: dict[tuple[int, int, int], str] = {}
    aliases_by_modifier_id: dict[int, set[str]] = defaultdict(set)

    for modifier_ids_for_base in ids_by_base_name.values():
        modifier_ids_for_base = sorted(modifier_ids_for_base)
        if len(modifier_ids_for_base) == 1:
            modifier_id = modifier_ids_for_base[0]
            base_label = canonical_metadata_by_id[modifier_id]["base_label"]
            aliases_by_modifier_id[modifier_id].add(base_label)
            for occurrence_key in occurrences_by_modifier_id.get(modifier_id, []):
                occurrence_label_by_key[occurrence_key] = base_label
            continue

        records: list[dict[str, Any]] = []
        for modifier_id in modifier_ids_for_base:
            group_labels = sorted(
                group_labels_by_modifier_id.get(modifier_id, set()),
                key=lambda value: (normalize_name(value), value),
            )
            if not group_labels:
                group_labels = [""]

            metadata = canonical_metadata_by_id[modifier_id]
            for group_label in group_labels:
                records.append(
                    {
                        "key": (modifier_id, group_label),
                        "modifier_id": modifier_id,
                        "group_label": group_label,
                        "base_label": metadata["base_label"],
                        "category_label": metadata["category_label"],
                        "description_label": metadata["description_label"],
                    }
                )

        labels_by_record_key = _assign_qualified_labels(
            records,
            qualifier_fields=["group_label", "category_label", "description_label"],
        )

        labels_by_modifier_and_group: dict[tuple[int, str], str] = {}
        for record in records:
            modifier_id = record["modifier_id"]
            group_label = record["group_label"]
            label = labels_by_record_key[record["key"]]
            labels_by_modifier_and_group[(modifier_id, group_label)] = label
            aliases_by_modifier_id[modifier_id].add(label)

        for modifier_id in modifier_ids_for_base:
            fallback_labels = sorted(
                aliases_by_modifier_id[modifier_id],
                key=lambda value: (normalize_name(value), value),
            )
            for occurrence_key in occurrences_by_modifier_id.get(modifier_id, []):
                group_label = occurrence_group_label_by_key.get(occurrence_key, "")
                occurrence_label = labels_by_modifier_and_group.get(
                    (modifier_id, group_label)
                )
                if occurrence_label is None:
                    occurrence_label = (
                        fallback_labels[0]
                        if fallback_labels
                        else canonical_metadata_by_id[modifier_id]["base_label"]
                    )
                occurrence_label_by_key[occurrence_key] = occurrence_label

    aliases_by_modifier_id_list = {
        modifier_id: sorted(
            labels,
            key=lambda value: (normalize_name(value), value),
        )
        for modifier_id, labels in aliases_by_modifier_id.items()
    }

    for occurrence_key, group_label in occurrence_group_label_by_key.items():
        if occurrence_key in occurrence_label_by_key:
            continue
        modifier_id = occurrence_key[2]
        fallback_aliases = aliases_by_modifier_id_list.get(modifier_id, [])
        if fallback_aliases:
            occurrence_label_by_key[occurrence_key] = fallback_aliases[0]
            continue

        base_label = canonical_metadata_by_id.get(modifier_id, {}).get("base_label")
        if base_label:
            occurrence_label_by_key[occurrence_key] = base_label
            aliases_by_modifier_id_list[modifier_id] = [base_label]
            continue

        fallback_label = _append_qualifier(f"Modifier {modifier_id}", group_label)
        occurrence_label_by_key[occurrence_key] = fallback_label
        aliases_by_modifier_id_list[modifier_id] = [fallback_label]

    for modifier_id, metadata in canonical_metadata_by_id.items():
        if modifier_id in aliases_by_modifier_id_list:
            continue
        aliases_by_modifier_id_list[modifier_id] = [metadata["base_label"]]

    return occurrence_label_by_key, aliases_by_modifier_id_list


@dataclass(frozen=True)
class QualifiedNameMaps:
    """Qualified name indexes shared by compile and LLM menu scripts."""

    item_label_by_id: dict[int, str]
    modifier_occurrence_label: dict[tuple[int, int, int], str]
    modifier_aliases_by_id: dict[int, list[str]]


def build_qualified_name_maps(raw_menu: dict[str, Any]) -> QualifiedNameMaps:
    """Build deterministic label maps for ambiguous item/modifier names."""
    size_name_by_id = _build_size_name_by_id(raw_menu)
    category_name_by_id = _build_category_name_by_id(raw_menu)
    web_category_name_by_id = _build_web_category_name_by_id(raw_menu)
    modifier_category_name_by_id = _build_modifier_category_name_by_id(raw_menu)
    top_group_name_by_id = _build_top_group_name_by_id(raw_menu)

    item_label_by_id = _build_item_label_by_id(
        raw_menu,
        size_name_by_id=size_name_by_id,
        category_name_by_id=category_name_by_id,
        web_category_name_by_id=web_category_name_by_id,
    )
    modifier_occurrence_label, modifier_aliases_by_id = _build_modifier_labels(
        raw_menu,
        modifier_category_name_by_id=modifier_category_name_by_id,
        top_group_name_by_id=top_group_name_by_id,
    )

    return QualifiedNameMaps(
        item_label_by_id=item_label_by_id,
        modifier_occurrence_label=modifier_occurrence_label,
        modifier_aliases_by_id=modifier_aliases_by_id,
    )
