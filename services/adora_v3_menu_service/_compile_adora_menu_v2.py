"""Compile raw Adora menu JSON with deterministic qualified-name disambiguation.

Usage:
    uv run python scripts/compile_adora_menu_v2.py
    uv run python scripts/compile_adora_menu_v2.py --input raw_menu.json --output compiled_menu.json
    cat raw_menu.json | uv run python scripts/compile_adora_menu_v2.py --input - --output -
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from pal_agents.providers.adora._implementation import AdoraCompiledMenuV1

from ._adora_name_qualifiers import build_qualified_name_maps, clean_name

TAKEOUT_ORDER_TYPE_ID = 2
DELIVERY_ORDER_TYPE_ID = 3
NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")


def _normalize_name(value: str) -> str:
    """Normalize user-facing names into canonical lookup keys."""
    return NORMALIZATION_PATTERN.sub(" ", value.casefold()).strip()


def _load_json_object(path_or_stdin: str) -> dict[str, Any]:
    """Load a JSON object from a file path or stdin ("-")."""
    if path_or_stdin == "-":
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin is empty")
        data = json.loads(raw)
    else:
        path = Path(path_or_stdin).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object")
    return data


def compile_menu_v2(raw_menu: dict[str, Any]) -> dict[str, Any]:
    """Compile raw Adora menu payload into deterministic schema V1 with qualified names."""
    store_id = raw_menu.get("store_id")
    if not isinstance(store_id, str) or not store_id.strip():
        raise ValueError("Raw menu must contain a non-empty string store_id")

    qualified_names = build_qualified_name_maps(raw_menu)

    sizes_by_name: dict[str, set[int]] = defaultdict(set)
    for size in raw_menu.get("sizes", []):
        if not isinstance(size, dict):
            continue
        size_id = size.get("size_id")
        size_name = size.get("name")
        if isinstance(size_id, int) and isinstance(size_name, str):
            normalized = _normalize_name(size_name)
            if normalized:
                sizes_by_name[normalized].add(size_id)

    modifiers_by_name: dict[str, set[int]] = defaultdict(set)
    for modifier in raw_menu.get("modifiers", []):
        if not isinstance(modifier, dict):
            continue
        modifier_id = modifier.get("modifier_id")
        if not isinstance(modifier_id, int):
            continue

        aliases = qualified_names.modifier_aliases_by_id.get(modifier_id)
        if not aliases:
            fallback_name = clean_name(modifier.get("name"))
            aliases = [fallback_name] if fallback_name else []
        for alias in aliases:
            normalized = _normalize_name(alias)
            if normalized:
                modifiers_by_name[normalized].add(modifier_id)

    modifier_weights_by_id: dict[int, dict[str, Any]] = {}
    for weight in raw_menu.get("modifier_weights", []):
        if not isinstance(weight, dict):
            continue

        modifier_weight_id = weight.get("modifier_weight_id")
        name = weight.get("name")
        if not isinstance(modifier_weight_id, int) or not isinstance(name, str):
            continue

        normalized_name = name.strip()
        if not normalized_name:
            continue

        existing = modifier_weights_by_id.get(modifier_weight_id)
        if existing is None:
            modifier_weights_by_id[modifier_weight_id] = {
                "name": normalized_name,
                "default": bool(weight.get("default")),
            }
            continue

        if existing["name"] != normalized_name:
            raise ValueError(
                "Conflicting modifier weight name for "
                f"modifier_weight_id={modifier_weight_id}: "
                f"{existing['name']!r} != {normalized_name!r}"
            )
        existing["default"] = bool(existing["default"]) or bool(weight.get("default"))

    if not modifier_weights_by_id:
        raise ValueError("Raw menu must contain at least one modifier_weights entry")

    items_by_name: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for raw_item in raw_menu.get("items", []):
        if not isinstance(raw_item, dict):
            continue

        item_id = raw_item.get("item_id")
        item_name = raw_item.get("name")
        if not isinstance(item_id, int) or not isinstance(item_name, str):
            continue

        qualified_item_name = qualified_names.item_label_by_id.get(
            item_id, clean_name(item_name)
        )
        normalized_item_name = _normalize_name(qualified_item_name)
        if not normalized_item_name:
            continue

        takeout_size_by_id: dict[int, bool] = {}
        delivery_size_by_id: dict[int, bool] = {}
        for order_type in raw_item.get("order_types", []):
            if not isinstance(order_type, dict):
                continue
            order_type_id = order_type.get("order_type_id")
            if not isinstance(order_type_id, int):
                continue
            if order_type_id == TAKEOUT_ORDER_TYPE_ID:
                sizes_for_order_type = takeout_size_by_id
            elif order_type_id == DELIVERY_ORDER_TYPE_ID:
                sizes_for_order_type = delivery_size_by_id
            else:
                continue
            for size_entry in order_type.get("sizes", []):
                if not isinstance(size_entry, dict):
                    continue
                size_id = size_entry.get("size_id")
                if not isinstance(size_id, int):
                    continue

                allow_halving = bool(size_entry.get("allow_halving"))
                previous_allow_halving = sizes_for_order_type.get(size_id)
                if (
                    previous_allow_halving is not None
                    and previous_allow_halving != allow_halving
                ):
                    raise ValueError(
                        "Conflicting allow_halving values for "
                        f"item_id={item_id}, order_type_id={order_type_id}, size_id={size_id}"
                    )
                sizes_for_order_type[size_id] = allow_halving

        modifier_groups_by_id: dict[int, dict[str, Any]] = {}
        for group in raw_item.get("modifier_groups", []):
            if not isinstance(group, dict):
                continue
            group_id = group.get("modifier_group_id")
            if not isinstance(group_id, int):
                continue

            allow_halving = bool(group.get("allow_halving"))
            existing_group = modifier_groups_by_id.get(group_id)
            if existing_group is None:
                existing_group = {"allow_halving": allow_halving, "modifiers": {}}
                modifier_groups_by_id[group_id] = existing_group
            elif bool(existing_group["allow_halving"]) != allow_halving:
                raise ValueError(
                    "Conflicting allow_halving values for "
                    f"item_id={item_id}, modifier_group_id={group_id}"
                )

            group_modifiers = existing_group["modifiers"]
            if not isinstance(group_modifiers, dict):
                raise ValueError("Internal error: modifier map must be a dict")

            for modifier in group.get("modifiers", []):
                if not isinstance(modifier, dict):
                    continue
                modifier_id = modifier.get("modifier_id")
                if not isinstance(modifier_id, int):
                    continue

                existing_default = bool(group_modifiers.get(modifier_id, False))
                group_modifiers[modifier_id] = existing_default or bool(
                    modifier.get("default")
                )

        compiled_modifier_groups = []
        for group_id in sorted(modifier_groups_by_id):
            group_entry = modifier_groups_by_id[group_id]
            group_modifiers = group_entry["modifiers"]
            if not isinstance(group_modifiers, dict):
                raise ValueError("Internal error: modifier map must be a dict")

            compiled_modifier_groups.append(
                {
                    "modifier_group_id": group_id,
                    "allow_halving": bool(group_entry["allow_halving"]),
                    "modifiers": [
                        {
                            "modifier_id": modifier_id,
                            "default": bool(group_modifiers[modifier_id]),
                        }
                        for modifier_id in sorted(group_modifiers)
                    ],
                }
            )

        compiled_item = {
            "item_id": item_id,
            "allow_halving": bool(raw_item.get("allow_halving")),
            "takeout_sizes": [
                {"size_id": size_id, "allow_halving": allow_halving}
                for size_id, allow_halving in sorted(takeout_size_by_id.items())
            ],
            "delivery_sizes": [
                {"size_id": size_id, "allow_halving": allow_halving}
                for size_id, allow_halving in sorted(delivery_size_by_id.items())
            ],
            "modifier_groups": compiled_modifier_groups,
        }

        existing_item = items_by_name[normalized_item_name].get(item_id)
        if existing_item is not None and existing_item != compiled_item:
            raise ValueError(
                f"Conflicting definitions for normalized item={normalized_item_name!r}, "
                f"item_id={item_id}"
            )
        items_by_name[normalized_item_name][item_id] = compiled_item

    return {
        "version": 1,
        "store_id": store_id.strip(),
        "sizes": {
            normalized_name: sorted(size_ids)
            for normalized_name, size_ids in sorted(sizes_by_name.items())
        },
        "modifiers": {
            normalized_name: sorted(modifier_ids)
            for normalized_name, modifier_ids in sorted(modifiers_by_name.items())
        },
        "items": {
            normalized_name: [
                items_for_name[item_id] for item_id in sorted(items_for_name)
            ]
            for normalized_name, items_for_name in sorted(items_by_name.items())
        },
        "modifier_weights": [
            {
                "modifier_weight_id": modifier_weight_id,
                "name": modifier_weights_by_id[modifier_weight_id]["name"],
                "default": bool(modifier_weights_by_id[modifier_weight_id]["default"]),
            }
            for modifier_weight_id in sorted(modifier_weights_by_id)
        ],
    }


def compile_menu_v1(raw_menu: dict[str, Any]) -> dict[str, Any]:
    """Back-compat alias for callers expecting the old function name."""
    return compile_menu_v2(raw_menu)


def _build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Compile Adora raw menu JSON into canonical precompiled schema V1 "
            "with qualified name disambiguation."
        )
    )
    parser.add_argument(
        "--input",
        default="brenz_newalbany.json",
        help='Raw Adora menu JSON path, or "-" for stdin.',
    )
    parser.add_argument(
        "--output",
        default="brenz_menu_compiled_v2.json",
        help='Compiled output JSON path, or "-" for stdout.',
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate output JSON against compiled schema V1 before writing.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print compilation stats to stderr.",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""
    parser = _build_parser()
    args = parser.parse_args()

    try:
        raw_menu = _load_json_object(args.input)
        compiled = compile_menu_v2(raw_menu)

        if args.validate:
            compiled = AdoraCompiledMenuV1.model_validate(compiled).model_dump(
                mode="python"
            )

        rendered = (
            json.dumps(compiled, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        )

        if args.output == "-":
            sys.stdout.write(rendered)
        else:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")

        if args.stats:
            item_count = sum(
                len(item_entries) for item_entries in compiled.get("items", {}).values()
            )
            print(f"store_id: {compiled.get('store_id', '')}", file=sys.stderr)
            print(f"items: {item_count}", file=sys.stderr)
            print(f"sizes: {len(compiled.get('sizes', {}))}", file=sys.stderr)
            print(f"modifiers: {len(compiled.get('modifiers', {}))}", file=sys.stderr)
            print(f"output_bytes: {len(rendered.encode('utf-8'))}", file=sys.stderr)

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
