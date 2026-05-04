"""Convert Toast case-spec JSON → pal-mono eval scenario YAML.

Input: case-spec JSON as produced by `pal-agents` local-loop tooling — a file
with the shape::

    {
      "agent_id": "sonnys_bbq",
      "cases": [
        {
          "id": "case_id",
          "test_category": "required_selection" | "simple_no_modifiers",
          "context": ["Customer's opening utterance."],
          "items": [
            {
              "item": "Menu Item",
              "quantity": 1,
              "selections": [
                {"steps": [{"group": "Group", "option": "Option",
                            "qualifier": null}]}
              ]
            }
          ]
        }
      ]
    }

Output: a YAML list of ``EvalScenario``-shaped dicts (see
``services/eval_service/schema.py``). Each case becomes one scenario with:

- ``user_turns`` = the opening utterance plus an ``ai_driven`` turn with a
  persona goal that lists the ordered items.
- ``expected_tool_calls`` = an optional ``get_toast_item_details_v3`` lookup
  (only when the case has at least one selection) followed by a required
  ``toast_takeout_create_order_v1`` call carrying the full ``selection_paths``.

The converter is intentionally pure/stateless: no I/O beyond the explicit
``convert_case_spec_file`` entrypoint. CLI usage::

    uv run python -m services.eval_service.scripts.convert_case_specs \\
        path/to/case_spec.json path/to/scenarios.yaml
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, cast

import yaml

__all__ = [
    "HARD_RULES",
    "DEFAULT_CUSTOMER",
    "build_items_summary",
    "build_lookup_targets",
    "build_selection_paths",
    "clean_item_for_speech",
    "clean_option_for_speech",
    "convert_case",
    "convert_case_spec_file",
]


HARD_RULES: str = """Hard rules:
- Only provide name and phone when the agent asks for them.
- Do not use exact Toast group or option labels unless the agent says them first.
- Do not volunteer your phone number until asked.
- Never add toppings, halves, sauces, sides, timing, or modifiers that are not in the expected order.
- If the agent asks for a detail that is not in the expected order, ask for the standard or default version instead of inventing one.
- Keep replies to one or two short sentences.
- When the agent confirms the order or asks to place it, say yes.
- When the order is placed and the agent says goodbye, end the conversation."""

DEFAULT_CUSTOMER: dict[str, str] = {
    "first_name": "Taylor",
    "last_name": "Parker",
    "phone": "5551234567",
}

_DEFAULT_MAX_TURNS: int = 14

_OPTION_STRIP_PATTERNS: tuple[str, ...] = (
    r"\s*\(\.\d+\)",  # (.32), (.25), (.50)
    r"\s*\([0-9]+LB\)",  # (1LB)
    r"\s*\([0-9]+\.[0-9]+LB\)",  # (1.5LB)
    r"\s*\(MOD\)",  # (MOD)
    r"\s*\(Kid[\u2019']?s?\)",  # (Kid), (Kids), (Kid's), (Kid\u2019s)
    r"\s*\(KIds\)",  # (KIds) typo variant in inventory
    r"\s*\(Add On\)",  # (Add On)
    r"\s*\(Upgrade\)",  # (Upgrade)
    r"\s*\(3PD\)",  # (3PD)
    r"\s*\(FAM\)",  # (FAM)
    r"\s*\(Salad\)",  # (Salad)
    r"\s*\(Dinner\)",  # (Dinner)
    r"\s*\([0-9]+\)",  # (2), (4), (6), (8), (10)
    r"\s*\(Test\)",  # (Test)
)

_ITEM_STRIP_PATTERNS: tuple[str, ...] = (
    r"\s*\(Signature BBQ\)",
    r"\s*\(Dinner\)",
    r"\s*\(Olo[^)]*\)",
)


def clean_option_for_speech(option: str) -> str:
    """Strip internal Toast codes from *option* for natural-language summaries.

    Preserves the original string for tool payloads; only the human-facing
    persona/goal summaries use this cleaner.
    """
    cleaned = option
    for pattern in _OPTION_STRIP_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"^Regular\s*-\s*", "", cleaned)
    return cleaned.strip()


def clean_item_for_speech(item: str) -> str:
    """Strip internal category tags from *item* for natural-language summaries."""
    cleaned = item
    for pattern in _ITEM_STRIP_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    return cleaned.strip()


def build_items_summary(items: list[dict[str, Any]]) -> str:
    """Render a short comma-separated summary of items for the persona goal.

    For each item we quote the item name plus the terminal selected options
    across every selection. Internal codes are stripped for readability.
    """
    parts: list[str] = []
    for item in items:
        name = clean_item_for_speech(str(item.get("item", "")))
        quantity = int(item.get("quantity", 1))
        prefix = f"{quantity}x " if quantity > 1 else "a "
        options: list[str] = []
        for selection in item.get("selections", []):
            steps: list[dict[str, Any]] = selection.get("steps", [])
            if not steps:
                continue
            terminal_option = str(steps[-1].get("option", ""))
            cleaned = clean_option_for_speech(terminal_option)
            if cleaned:
                options.append(cleaned)
        if options:
            parts.append(f"{prefix}{name} with {', '.join(options)}")
        else:
            parts.append(f"{prefix}{name}")
    return "; ".join(parts)


def build_lookup_targets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect one ``targets[]`` entry per touched top-level group per item.

    Returns a list suitable for the ``items`` argument of a
    ``get_toast_item_details_v3`` call. Items without selections are skipped.
    """
    lookup_items: list[dict[str, Any]] = []
    for item in items:
        top_groups: list[str] = []
        seen: set[str] = set()
        for selection in item.get("selections", []):
            steps: list[dict[str, Any]] = selection.get("steps", [])
            if not steps:
                continue
            top_group = str(steps[0].get("group", ""))
            if top_group and top_group not in seen:
                seen.add(top_group)
                top_groups.append(top_group)
        if not top_groups:
            continue
        lookup_items.append(
            {
                "item_name": str(item["item"]),
                "targets": [
                    {"group_name": group, "path_prefix": []} for group in top_groups
                ],
            }
        )
    return lookup_items


def build_selection_paths(
    selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert spec ``selections[{steps:[...]}]`` → scenario ``selection_paths``."""
    paths: list[dict[str, Any]] = []
    for selection in selections:
        steps: list[dict[str, Any]] = selection.get("steps", [])
        if not steps:
            continue
        path_steps: list[dict[str, Any]] = []
        for step in steps:
            entry: dict[str, Any] = {
                "group_name": str(step["group"]),
                "option_name": str(step["option"]),
            }
            qualifier = step.get("qualifier")
            if qualifier:
                entry["qualifier"] = qualifier
            path_steps.append(entry)
        paths.append({"path": path_steps})
    return paths


def convert_case(
    case: dict[str, Any],
    customer: dict[str, str] | None = None,
    max_turns: int = _DEFAULT_MAX_TURNS,
) -> dict[str, Any]:
    """Convert one case-spec entry into a scenario dict.

    The returned dict matches the ``EvalScenario`` schema exactly so it can be
    validated via ``services.eval_service._scenario_loader.validate_scenarios_from_yaml``.
    """
    if customer is None:
        customer = DEFAULT_CUSTOMER
    items: list[dict[str, Any]] = list(case.get("items", []))
    raw_context = case.get("context", [])
    if isinstance(raw_context, str):
        context_list: list[str] = [raw_context]
    elif isinstance(raw_context, list):
        context_list = [str(c) for c in raw_context]
    else:
        context_list = []
    opening_utterance = context_list[0] if context_list else ""
    summary = build_items_summary(items)
    persona_line = (
        f"A straightforward phone customer named "
        f"{customer['first_name']} {customer['last_name']} "
        f"(phone {customer['phone']}). They want "
        f"{summary} for pickup. Friendly and concise."
    )
    goal_text = (
        f"Complete the order for {summary} for pickup. "
        f"Your name is {customer['first_name']} {customer['last_name']}, "
        f"phone {customer['phone']}.\n\n{HARD_RULES}"
    )

    scenario: dict[str, Any] = {
        "scenario_id": str(case["id"]),
        "scenario": opening_utterance,
        "test_category": str(case.get("test_category", "required_selection")),
        "max_turns": max_turns,
        "persona": persona_line,
        "user_turns": [
            opening_utterance or "Hi, I'd like to place an order for pickup",
            {"type": "ai_driven", "goal": goal_text},
        ],
        "expected_tool_calls": [],
    }

    lookup_items = build_lookup_targets(items)
    if lookup_items:
        cast(list[dict[str, Any]], scenario["expected_tool_calls"]).append(
            {
                "tool": "get_toast_item_details_v3",
                "optional": True,
                "args": {"items": lookup_items},
            }
        )

    order_items = [
        {
            "item_name": str(item["item"]),
            "quantity": int(item.get("quantity", 1)),
            "selection_paths": build_selection_paths(item.get("selections", [])),
        }
        for item in items
    ]
    cast(list[dict[str, Any]], scenario["expected_tool_calls"]).append(
        {
            "tool": "toast_takeout_create_order_v1",
            "args": {"customer": dict(customer), "items": order_items},
        }
    )

    scenario["expected_outcomes"] = {"task_completed": True}
    scenario["context"] = [opening_utterance] if opening_utterance else []
    return scenario


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    """Emit multi-line strings as block scalars for readability."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _build_dumper() -> type[yaml.SafeDumper]:
    """Return a ``SafeDumper`` subclass configured with the string representer."""

    class _Dumper(yaml.SafeDumper):
        pass

    _Dumper.add_representer(str, _str_representer)
    return _Dumper


def convert_case_spec_file(
    src: Path,
    dst: Path,
    customer: dict[str, str] | None = None,
    max_turns: int = _DEFAULT_MAX_TURNS,
) -> int:
    """Convert a case-spec JSON file to a scenarios YAML file.

    Returns the number of scenarios written.
    """
    raw = json.loads(src.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = list(raw.get("cases", []))
    scenarios = [
        convert_case(case, customer=customer, max_turns=max_turns) for case in cases
    ]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        yaml.dump(
            scenarios,
            Dumper=_build_dumper(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=120,
        ),
        encoding="utf-8",
    )
    return len(scenarios)


def _positive_int(value: str) -> int:
    """argparse ``type`` function: accept only positive integers (>= 1)."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("--max-turns must be >= 1")
    return parsed


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Toast case-spec JSON to eval scenario YAML.",
    )
    parser.add_argument("src", type=Path, help="Path to case-spec JSON.")
    parser.add_argument("dst", type=Path, help="Path to output YAML.")
    parser.add_argument(
        "--max-turns",
        type=_positive_int,
        default=_DEFAULT_MAX_TURNS,
        help="Max turns per scenario (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    count = convert_case_spec_file(src=args.src, dst=args.dst, max_turns=args.max_turns)
    print(f"wrote {count} scenarios → {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
