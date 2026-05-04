"""Tests for services/eval_service/scripts/convert_case_specs.py.

Covers:
- Helper cleaners strip internal Toast codes for speech but preserve the raw
  strings that end up in tool payloads.
- ``convert_case`` emits a scenario that validates against ``EvalScenario`` and
  includes an optional lookup call only when selections are present.
- ``convert_case_spec_file`` writes YAML that re-parses into matching
  scenario objects.
- Missing ``cases`` key is handled gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from services.eval_service._scenario_loader import validate_scenarios_from_yaml
from services.eval_service.schema import EvalScenario, TurnType, UserTurn
from services.eval_service.scripts.convert_case_specs import (
    DEFAULT_CUSTOMER,
    HARD_RULES,
    build_items_summary,
    build_lookup_targets,
    build_selection_paths,
    clean_item_for_speech,
    clean_option_for_speech,
    convert_case,
    convert_case_spec_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _required_selection_case() -> dict[str, object]:
    """A case-spec with one item, three selections across two top-level groups."""
    return {
        "id": "1_4_chicken_lunch_12242ad5",
        "test_category": "required_selection",
        "context": [
            "I'd like a 1/4 Chicken Lunch with BBQ Beans; Corn Bread; "
            "All White Meat (1/4)."
        ],
        "items": [
            {
                "item": "1/4 Chicken Lunch",
                "quantity": 1,
                "selections": [
                    {
                        "steps": [
                            {
                                "group": "Your Choice of Sidekicks 2",
                                "option": "Original Recipe BBQ Beans",
                            }
                        ]
                    },
                    {
                        "steps": [
                            {
                                "group": "Your Choice of Bread",
                                "option": "Corn Bread",
                            }
                        ]
                    },
                    {
                        "steps": [
                            {
                                "group": "Lunch - Chicken Options",
                                "option": "All White Meat (1/4)",
                            }
                        ]
                    },
                ],
            }
        ],
    }


def _simple_no_modifiers_case() -> dict[str, object]:
    """A case-spec with an item that has no selections."""
    return {
        "id": "baked_potato_9ee9c0c7",
        "test_category": "simple_no_modifiers",
        "context": ["I'd like a Baked Potato."],
        "items": [
            {
                "item": "Baked Potato",
                "quantity": 1,
                "selections": [],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Speech cleaners
# ---------------------------------------------------------------------------


class TestCleaners:
    def test_clean_option_strips_weight_codes(self) -> None:
        assert clean_option_for_speech("Pulled Pork (.32)") == "Pulled Pork"
        assert clean_option_for_speech("Sliced Pork (.25)") == "Sliced Pork"

    def test_clean_option_strips_mod_and_kids_tags(self) -> None:
        assert clean_option_for_speech("Sprite (MOD)") == "Sprite"
        assert clean_option_for_speech("Coca-Cola (Kids)") == "Coca-Cola"
        assert clean_option_for_speech("Coca-Cola (Kid)") == "Coca-Cola"
        # Apostrophe variants: both ASCII and curly.
        assert clean_option_for_speech("Coca-Cola (Kid's)") == "Coca-Cola"
        assert clean_option_for_speech("Coca-Cola (Kid\u2019s)") == "Coca-Cola"

    def test_clean_option_strips_regular_prefix(self) -> None:
        assert (
            clean_option_for_speech("Regular - Pulled Pork Sandwich (3PD)")
            == "Pulled Pork Sandwich"
        )

    def test_clean_option_preserves_plain_label(self) -> None:
        assert clean_option_for_speech("Homemade Coleslaw") == "Homemade Coleslaw"

    def test_clean_item_strips_signature_bbq(self) -> None:
        assert clean_item_for_speech("Beef Brisket (Signature BBQ)") == "Beef Brisket"
        assert clean_item_for_speech("Chicken Tenders (Dinner)") == "Chicken Tenders"

    def test_clean_item_strips_olo_variants(self) -> None:
        assert (
            clean_item_for_speech("Pork & Rib Combo (Olo - Founder's Month)")
            == "Pork & Rib Combo"
        )


# ---------------------------------------------------------------------------
# Summary + target builders
# ---------------------------------------------------------------------------


class TestBuilders:
    def test_build_items_summary_single_item(self) -> None:
        items = [
            {
                "item": "1/4 Chicken Lunch",
                "quantity": 1,
                "selections": [
                    {
                        "steps": [
                            {
                                "group": "Your Choice of Sidekicks 2",
                                "option": "Homemade Coleslaw",
                            }
                        ]
                    }
                ],
            }
        ]
        summary = build_items_summary(items)
        assert summary == "a 1/4 Chicken Lunch with Homemade Coleslaw"

    def test_build_items_summary_quantity_greater_than_one(self) -> None:
        items = [{"item": "Corn Bread", "quantity": 3, "selections": []}]
        assert build_items_summary(items) == "3x Corn Bread"

    def test_build_items_summary_no_selections(self) -> None:
        items = [{"item": "Baked Potato", "quantity": 1, "selections": []}]
        assert build_items_summary(items) == "a Baked Potato"

    def test_build_lookup_targets_dedupes_top_groups(self) -> None:
        items = [
            {
                "item": "Pick 4 Combo",
                "quantity": 1,
                "selections": [
                    {
                        "steps": [
                            {
                                "group": "Pick 4 Meat Options",
                                "option": "Pulled Pork (.32)",
                            }
                        ]
                    },
                    {
                        "steps": [
                            {
                                "group": "Pick 4 Meat Options",
                                "option": "Pulled Chicken (.32)",
                            }
                        ]
                    },
                    {
                        "steps": [
                            {"group": "Your Choice of Bread", "option": "Corn Bread"}
                        ]
                    },
                ],
            }
        ]
        targets = build_lookup_targets(items)
        assert len(targets) == 1
        assert targets[0]["item_name"] == "Pick 4 Combo"
        group_names = [t["group_name"] for t in targets[0]["targets"]]
        assert group_names == ["Pick 4 Meat Options", "Your Choice of Bread"]

    def test_build_lookup_targets_skips_items_with_no_selections(self) -> None:
        assert build_lookup_targets([{"item": "Baked Potato", "selections": []}]) == []

    def test_build_selection_paths_multi_step(self) -> None:
        selections = [
            {
                "steps": [
                    {
                        "group": "Your Choice of Sandwiches 2",
                        "option": "Regular - Pulled Pork Sandwich (3PD)",
                    },
                    {
                        "group": "Your Choice of Bread - Sandwiches (2 - 3PD)",
                        "option": "Corn Bread",
                    },
                ]
            }
        ]
        paths = build_selection_paths(selections)
        assert len(paths) == 1
        assert paths[0] == {
            "path": [
                {
                    "group_name": "Your Choice of Sandwiches 2",
                    "option_name": "Regular - Pulled Pork Sandwich (3PD)",
                },
                {
                    "group_name": "Your Choice of Bread - Sandwiches (2 - 3PD)",
                    "option_name": "Corn Bread",
                },
            ]
        }

    def test_build_selection_paths_passes_through_qualifier(self) -> None:
        selections = [
            {
                "steps": [
                    {
                        "group": "Toppings",
                        "option": "Pepperoni",
                        "qualifier": "LEFT SIDE",
                    }
                ]
            }
        ]
        paths = build_selection_paths(selections)
        assert paths[0]["path"][0]["qualifier"] == "LEFT SIDE"


# ---------------------------------------------------------------------------
# convert_case
# ---------------------------------------------------------------------------


class TestConvertCase:
    def test_required_selection_case_has_lookup_and_order_calls(self) -> None:
        scenario = convert_case(_required_selection_case())

        assert scenario["scenario_id"] == "1_4_chicken_lunch_12242ad5"
        assert scenario["test_category"] == "required_selection"
        assert scenario["max_turns"] == 14
        expected_opener = _required_selection_case()["context"]
        assert isinstance(expected_opener, list)
        assert scenario["user_turns"][0] == expected_opener[0]

        ai_turn = scenario["user_turns"][1]
        assert ai_turn["type"] == "ai_driven"
        assert "1/4 Chicken Lunch" in ai_turn["goal"]
        assert HARD_RULES in ai_turn["goal"]

        tool_calls = scenario["expected_tool_calls"]
        assert [c["tool"] for c in tool_calls] == [
            "get_toast_item_details_v3",
            "toast_takeout_create_order_v1",
        ]
        assert tool_calls[0]["optional"] is True

        order = tool_calls[1]
        assert order["args"]["customer"] == DEFAULT_CUSTOMER
        assert len(order["args"]["items"]) == 1
        assert len(order["args"]["items"][0]["selection_paths"]) == 3

    def test_simple_no_modifiers_case_omits_lookup(self) -> None:
        scenario = convert_case(_simple_no_modifiers_case())

        tool_calls = scenario["expected_tool_calls"]
        assert [c["tool"] for c in tool_calls] == ["toast_takeout_create_order_v1"]
        order = tool_calls[0]
        assert order["args"]["items"][0]["selection_paths"] == []

    def test_custom_customer_is_used(self) -> None:
        customer = {
            "first_name": "Alex",
            "last_name": "Rivera",
            "phone": "5559876543",
        }
        scenario = convert_case(_simple_no_modifiers_case(), customer=customer)
        order = scenario["expected_tool_calls"][0]
        assert order["args"]["customer"] == customer
        assert "Alex Rivera" in scenario["persona"]

    def test_output_validates_against_eval_scenario_schema(self) -> None:
        scenario = convert_case(_required_selection_case())
        validated = EvalScenario.model_validate(scenario)
        assert validated.scenario_id == scenario["scenario_id"]
        assert isinstance(validated.user_turns[1], UserTurn)
        assert validated.user_turns[1].type == TurnType.AI_DRIVEN


# ---------------------------------------------------------------------------
# File-level conversion
# ---------------------------------------------------------------------------


class TestConvertCaseSpecFile:
    def test_writes_valid_yaml_that_loads_as_scenarios(self, tmp_path: Path) -> None:
        spec = {
            "agent_id": "sonnys_bbq",
            "cases": [
                _required_selection_case(),
                _simple_no_modifiers_case(),
            ],
        }
        src = tmp_path / "spec.json"
        dst = tmp_path / "scenarios.yaml"
        src.write_text(json.dumps(spec), encoding="utf-8")

        count = convert_case_spec_file(src=src, dst=dst)

        assert count == 2
        loaded = validate_scenarios_from_yaml(dst)
        assert [s.scenario_id for s in loaded] == [
            "1_4_chicken_lunch_12242ad5",
            "baked_potato_9ee9c0c7",
        ]
        raw = yaml.safe_load(dst.read_text(encoding="utf-8"))
        assert isinstance(raw, list) and len(raw) == 2

    def test_empty_cases_yields_zero_scenarios(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        dst = tmp_path / "scenarios.yaml"
        src.write_text(
            json.dumps({"agent_id": "sonnys_bbq", "cases": []}), encoding="utf-8"
        )

        count = convert_case_spec_file(src=src, dst=dst)

        assert count == 0
        assert yaml.safe_load(dst.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestOpeningUtteranceFallback:
    def test_missing_context_falls_back_to_generic_greeting(self) -> None:
        """A case without ``context`` still produces a valid scenario.

        The first user turn falls back to the generic pickup greeting rather
        than producing an empty string (which ``EvalScenario`` / downstream
        consumers would treat as an absent utterance).
        """
        case = {
            "id": "no_context_case",
            "test_category": "simple_no_modifiers",
            "items": [{"item": "Baked Potato", "quantity": 1, "selections": []}],
        }

        scenario = convert_case(case)

        assert scenario["user_turns"][0] == "Hi, I'd like to place an order for pickup"
        # Still round-trips through EvalScenario.
        EvalScenario.model_validate(scenario)

    def test_string_context_not_split_into_characters(self) -> None:
        """If upstream sends ``context`` as a bare string (not a list), the
        whole string is treated as one utterance instead of being iterated
        character by character.
        """
        case = {
            "id": "string_context_case",
            "test_category": "simple_no_modifiers",
            "context": "Hi, I'd like a baked potato please.",
            "items": [{"item": "Baked Potato", "quantity": 1, "selections": []}],
        }

        scenario = convert_case(case)

        assert scenario["user_turns"][0] == "Hi, I'd like a baked potato please."
        assert scenario["context"] == ["Hi, I'd like a baked potato please."]
        EvalScenario.model_validate(scenario)


class TestCliMaxTurnsValidation:
    def test_zero_max_turns_rejected(self, tmp_path: Path, capsys: object) -> None:
        """``--max-turns 0`` exits with argparse error (EvalScenario requires >= 1)."""
        import pytest  # noqa: PLC0415 — local import keeps module top clean

        from services.eval_service.scripts.convert_case_specs import _main

        src = tmp_path / "spec.json"
        dst = tmp_path / "out.yaml"
        src.write_text(json.dumps({"cases": []}), encoding="utf-8")

        with pytest.raises(SystemExit):
            _main([str(src), str(dst), "--max-turns", "0"])

    def test_negative_max_turns_rejected(self, tmp_path: Path) -> None:
        import pytest  # noqa: PLC0415

        from services.eval_service.scripts.convert_case_specs import _main

        src = tmp_path / "spec.json"
        dst = tmp_path / "out.yaml"
        src.write_text(json.dumps({"cases": []}), encoding="utf-8")

        with pytest.raises(SystemExit):
            _main([str(src), str(dst), "--max-turns", "-3"])
