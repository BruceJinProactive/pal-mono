"""Tests for services/eval_service/evaluators/tool_call_args.py."""

from __future__ import annotations

from services.eval_service.evaluators.tool_call_args import (
    ToastArgumentEvaluator,
    _extract_args,
    _extract_tool_name,
    _get_evaluator,
    evaluate_tool_call_args,
)

# Shared instance for tests that call evaluator methods directly
_toast = ToastArgumentEvaluator()


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


class TestNormalizePhone:
    def test_strips_non_digits(self) -> None:
        assert _toast._normalize_phone("(555) 123-4567") == "5551234567"

    def test_already_digits(self) -> None:
        assert _toast._normalize_phone("5551234567") == "5551234567"

    def test_none_returns_none(self) -> None:
        assert _toast._normalize_phone(None) is None

    def test_empty_string(self) -> None:
        assert _toast._normalize_phone("") == ""


class TestNormalizeText:
    def test_collapses_whitespace(self) -> None:
        assert _toast._normalize_text("hello   world") == "hello world"

    def test_strips_leading_trailing(self) -> None:
        assert _toast._normalize_text("  hello  ") == "hello"

    def test_tabs_and_newlines(self) -> None:
        assert _toast._normalize_text("hello\t\nworld") == "hello world"

    def test_non_string_passthrough(self) -> None:
        assert _toast._normalize_text(42) == 42
        assert _toast._normalize_text(None) is None


# ---------------------------------------------------------------------------
# Field-level comparison
# ---------------------------------------------------------------------------


class TestCompareNamedValue:
    def test_matching_values(self) -> None:
        result = _toast._compare_named_value(
            field_path="customer.first_name", expected="John", actual="John"
        )
        assert result.matched is True

    def test_whitespace_normalized_match(self) -> None:
        result = _toast._compare_named_value(
            field_path="item_name",
            expected="Pepperoni  Pizza",
            actual="Pepperoni Pizza",
        )
        assert result.matched is True

    def test_mismatch(self) -> None:
        result = _toast._compare_named_value(
            field_path="customer.last_name", expected="Doe", actual="Smith"
        )
        assert result.matched is False
        assert "Doe" in result.detail
        assert "Smith" in result.detail


# ---------------------------------------------------------------------------
# Customer matching (via evaluate)
# ---------------------------------------------------------------------------


class TestToastEvaluateCustomer:
    def test_customer_fields_match(self) -> None:
        expected = {
            "customer": {
                "first_name": "John",
                "last_name": "Doe",
                "phone": "5551234567",
            }
        }
        actual = {
            "customer": {
                "first_name": "John",
                "last_name": "Doe",
                "phone": "5551234567",
            }
        }
        results = _toast.evaluate(expected, actual)
        assert all(d.matched for d in results)

    def test_phone_normalization(self) -> None:
        expected = {"customer": {"phone": "5551234567"}}
        actual = {"customer": {"phone": "(555) 123-4567"}}
        results = _toast.evaluate(expected, actual)
        phone_result = [d for d in results if d.field_path == "customer.phone"]
        assert len(phone_result) == 1
        assert phone_result[0].matched is True

    def test_phone_mismatch(self) -> None:
        expected = {"customer": {"phone": "5551234567"}}
        actual = {"customer": {"phone": "9999999999"}}
        results = _toast.evaluate(expected, actual)
        phone_result = [d for d in results if d.field_path == "customer.phone"]
        assert phone_result[0].matched is False

    def test_name_mismatch(self) -> None:
        expected = {"customer": {"first_name": "John"}}
        actual = {"customer": {"first_name": "Jane"}}
        results = _toast.evaluate(expected, actual)
        assert results[0].matched is False

    def test_skips_none_expected_fields(self) -> None:
        expected = {"customer": {}}
        actual = {"customer": {"first_name": "John"}}
        results = _toast.evaluate(expected, actual)
        assert len(results) == 0

    def test_camel_case_actual_matches_snake_case_expected(self) -> None:
        """Toast runtime sends camelCase; YAML scenarios use snake_case."""
        expected = {"customer": {"first_name": "John", "last_name": "Doe"}}
        actual = {"customer": {"firstName": "John", "lastName": "Doe"}}
        results = _toast.evaluate(expected, actual)
        assert all(d.matched for d in results)
        assert {d.field_path for d in results} == {
            "customer.first_name",
            "customer.last_name",
        }

    def test_camel_case_actual_mismatch(self) -> None:
        expected = {"customer": {"first_name": "John"}}
        actual = {"customer": {"firstName": "Jane"}}
        results = _toast.evaluate(expected, actual)
        assert results[0].matched is False


# ---------------------------------------------------------------------------
# Items matching
# ---------------------------------------------------------------------------


class TestCompareItems:
    def test_single_item_match(self) -> None:
        expected = [{"item_name": "Pepperoni Pizza", "quantity": 1}]
        actual = [{"item_name": "Pepperoni Pizza", "quantity": 1}]
        results = _toast._compare_items(expected, actual)
        assert all(d.matched for d in results)

    def test_item_name_whitespace_normalized(self) -> None:
        expected = [{"item_name": "Pepperoni  Pizza"}]
        actual = [{"item_name": "Pepperoni Pizza"}]
        results = _toast._compare_items(expected, actual)
        name_results = [d for d in results if "item_name" in d.field_path]
        assert name_results[0].matched is True

    def test_quantity_mismatch(self) -> None:
        expected = [{"item_name": "Pizza", "quantity": 2}]
        actual = [{"item_name": "Pizza", "quantity": 1}]
        results = _toast._compare_items(expected, actual)
        qty_results = [d for d in results if "quantity" in d.field_path]
        assert qty_results[0].matched is False

    def test_quantity_not_checked_when_not_in_expected(self) -> None:
        expected = [{"item_name": "Pizza"}]
        actual = [{"item_name": "Pizza", "quantity": 3}]
        results = _toast._compare_items(expected, actual)
        qty_results = [d for d in results if "quantity" in d.field_path]
        assert len(qty_results) == 0

    def test_item_count_mismatch(self) -> None:
        expected = [{"item_name": "Pizza"}, {"item_name": "Salad"}]
        actual = [{"item_name": "Pizza"}]
        results = _toast._compare_items(expected, actual)
        assert results[0].field_path == "items"
        assert results[0].matched is False
        assert "count mismatch" in results[0].detail

    def test_item_note_checked_when_present(self) -> None:
        expected = [{"item_name": "Pizza", "item_note": "extra cheese"}]
        actual = [{"item_name": "Pizza", "item_note": "extra cheese"}]
        results = _toast._compare_items(expected, actual)
        note_results = [d for d in results if "item_note" in d.field_path]
        assert len(note_results) == 1
        assert note_results[0].matched is True

    def test_item_note_mismatch(self) -> None:
        expected = [{"item_name": "Pizza", "item_note": "no onions"}]
        actual = [{"item_name": "Pizza", "item_note": "extra onions"}]
        results = _toast._compare_items(expected, actual)
        note_results = [d for d in results if "item_note" in d.field_path]
        assert note_results[0].matched is False


# ---------------------------------------------------------------------------
# Selection paths
# ---------------------------------------------------------------------------


class TestSelectionPaths:
    def test_matching_paths(self) -> None:
        expected = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Large"}]}
                ],
            }
        ]
        actual = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Large"}]}
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        assert all(d.matched for d in results)

    def test_path_mismatch(self) -> None:
        expected = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Large"}]}
                ],
            }
        ]
        actual = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Small"}]}
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        option_results = [d for d in results if "option_name" in d.field_path]
        assert any(not d.matched for d in option_results)

    def test_selection_path_count_mismatch(self) -> None:
        expected = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Large"}]},
                    {"path": [{"group_name": "Crust", "option_name": "Thin"}]},
                ],
            }
        ]
        actual = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Large"}]}
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        sp_results = [
            d
            for d in results
            if "selection_paths" in d.field_path and "count" in d.detail
        ]
        assert len(sp_results) == 1
        assert sp_results[0].matched is False

    def test_whitespace_normalized_path(self) -> None:
        expected = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Wing  Sauce", "option_name": "BBQ"}]}
                ],
            }
        ]
        actual = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Wing Sauce", "option_name": "BBQ"}]}
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        assert all(d.matched for d in results)


# ---------------------------------------------------------------------------
# _extract_tool_name / _extract_args
# ---------------------------------------------------------------------------


class TestExtractHelpers:
    def test_extract_tool_name_payload(self) -> None:
        tc = {"payload": {"tool_name": "toast.checkout", "arguments": {}}}
        assert _extract_tool_name(tc) == "toast.checkout"

    def test_extract_tool_name_flat(self) -> None:
        assert _extract_tool_name({"tool_name": "my_tool"}) == "my_tool"
        assert _extract_tool_name({"tool": "my_tool"}) == "my_tool"

    def test_extract_args_payload(self) -> None:
        tc = {"payload": {"tool_name": "t", "arguments": {"k": "v"}}}
        assert _extract_args(tc) == {"k": "v"}

    def test_extract_args_flat(self) -> None:
        assert _extract_args({"tool_name": "t", "args": {"k": "v"}}) == {"k": "v"}
        assert _extract_args({"tool": "t", "arguments": {"k": "v"}}) == {"k": "v"}


# ---------------------------------------------------------------------------
# evaluate_tool_call_args (top-level evaluator)
# ---------------------------------------------------------------------------


class TestEvaluateToolCallArgs:
    def test_perfect_match(self) -> None:
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "customer": {"first_name": "John", "phone": "5551234567"},
                    "items": [{"item_name": "Pizza", "quantity": 1}],
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {
                        "customer": {"first_name": "John", "phone": "555-123-4567"},
                        "items": [{"item_name": "Pizza", "quantity": 1}],
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0
        assert result.metric_name == "tool_call_accuracy"

    def test_partial_match(self) -> None:
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "customer": {"first_name": "John", "last_name": "Doe"},
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {
                        "customer": {"first_name": "John", "last_name": "Smith"}
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is False
        assert result.score == 0.5

    def test_tool_not_found(self) -> None:
        expected = [
            {"tool": "toast.missing_tool", "args": {"customer": {"first_name": "X"}}}
        ]
        actual = [{"type": "tool_call", "payload": {"tool_name": "toast.other"}}]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is False
        assert result.score == 0.0
        assert result.raw_output is not None
        assert "not called" in result.raw_output["match_details"][0]["detail"]

    def test_checkout_order_with_args_verifies_args(self) -> None:
        """checkout_order with args goes through ToastArgumentEvaluator."""
        expected = [
            {
                "tool": "checkout_order",
                "args": {
                    "customer": {
                        "first_name": "Sarah",
                        "last_name": "Miller",
                        "phone": "5551234567",
                    },
                    "items": [{"item_name": "Frozen Cheese", "quantity": 1}],
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "checkout_order",
                    "arguments": {
                        "customer": {
                            "firstName": "Sarah",
                            "lastName": "Miller",
                            "phone": "(555) 123-4567",
                        },
                        "items": [{"item_name": "Frozen Cheese", "quantity": 1}],
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0

    def test_no_args_verifies_tool_name_only(self) -> None:
        """When expected has no args, just verify the tool was called."""
        expected = [{"tool": "checkout_order", "args": {}}]
        actual = [{"tool_name": "checkout_order"}]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0

    def test_no_args_tool_missing_fails(self) -> None:
        """When expected has no args but tool wasn't called, it fails."""
        expected = [{"tool": "checkout_order", "args": {}}]
        actual: list[dict[str, object]] = []
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is False
        assert result.score == 0.0

    def test_no_expected_returns_pass(self) -> None:
        result = evaluate_tool_call_args([], [])
        assert result.passed is True
        assert result.reason == "No tool calls expected"

    def test_raw_output_contains_match_details(self) -> None:
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "customer": {"first_name": "John"},
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {"customer": {"first_name": "John"}},
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.raw_output is not None
        assert "match_details" in result.raw_output
        details = result.raw_output["match_details"]
        assert len(details) == 1
        assert details[0]["field"] == "customer.first_name"
        assert details[0]["matched"] is True

    def test_multi_item_order(self) -> None:
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "items": [
                        {"item_name": "Pizza", "quantity": 1},
                        {"item_name": "Salad", "quantity": 2},
                    ],
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {
                        "items": [
                            {"item_name": "Pizza", "quantity": 1},
                            {"item_name": "Salad", "quantity": 2},
                        ],
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0


# ---------------------------------------------------------------------------
# Multiple tool calls
# ---------------------------------------------------------------------------


class TestMultipleToolCalls:
    """Matching expected→actual with multiple unique tool names."""

    def test_two_different_tools(self) -> None:
        expected = [
            {
                "tool": "toast.checkout_order",
                "args": {"customer": {"first_name": "A"}},
            },
            {
                "tool": "toast.validate_order_intent",
                "args": {"customer": {"first_name": "B"}},
            },
        ]
        actual = [
            {
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {"customer": {"first_name": "B"}},
                }
            },
            {
                "payload": {
                    "tool_name": "toast.checkout_order",
                    "arguments": {"customer": {"firstName": "A"}},
                }
            },
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0


# ---------------------------------------------------------------------------
# Hard: selection path order-independence
# ---------------------------------------------------------------------------


class TestSelectionPathOrderIndependence:
    """Selection paths should match regardless of order in the array."""

    def test_two_paths_reversed_order(self) -> None:
        expected = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Size", "option_name": "Large"}]},
                    {"path": [{"group_name": "Crust", "option_name": "Thin"}]},
                ],
            }
        ]
        actual = [
            {
                "item_name": "Pizza",
                "selection_paths": [
                    {"path": [{"group_name": "Crust", "option_name": "Thin"}]},
                    {"path": [{"group_name": "Size", "option_name": "Large"}]},
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        assert all(d.matched for d in results)

    def test_three_paths_shuffled(self) -> None:
        paths_expected = [
            {"path": [{"group_name": "Size", "option_name": "Medium"}]},
            {"path": [{"group_name": "Sauce", "option_name": "Marinara"}]},
            {"path": [{"group_name": "Cheese", "option_name": "Extra"}]},
        ]
        paths_actual = [
            {"path": [{"group_name": "Cheese", "option_name": "Extra"}]},
            {"path": [{"group_name": "Size", "option_name": "Medium"}]},
            {"path": [{"group_name": "Sauce", "option_name": "Marinara"}]},
        ]
        results = _toast._compare_selection_paths(
            paths_expected, paths_actual, "items[0]"
        )
        assert all(d.matched for d in results)

    def test_order_independent_with_one_mismatch(self) -> None:
        """Two paths match, one has wrong option — should report exactly one failure."""
        paths_expected = [
            {"path": [{"group_name": "Size", "option_name": "Large"}]},
            {"path": [{"group_name": "Sauce", "option_name": "BBQ"}]},
        ]
        paths_actual = [
            {"path": [{"group_name": "Sauce", "option_name": "Ranch"}]},
            {"path": [{"group_name": "Size", "option_name": "Large"}]},
        ]
        results = _toast._compare_selection_paths(
            paths_expected, paths_actual, "items[0]"
        )
        matched = [d for d in results if d.matched]
        failed = [d for d in results if not d.matched]
        # Size matches (group_name + option_name), Sauce group matches but option differs
        assert len(matched) >= 2  # Size group+option
        assert any(not d.matched and "option_name" in d.field_path for d in failed)


# ---------------------------------------------------------------------------
# Hard: multi-step selection paths
# ---------------------------------------------------------------------------


class TestMultiStepSelectionPaths:
    """Selection paths with multiple steps in the path array."""

    def test_two_step_path_match(self) -> None:
        expected = [
            {
                "item_name": "Combo Meal",
                "selection_paths": [
                    {
                        "path": [
                            {"group_name": "Entree", "option_name": "Burger"},
                            {"group_name": "Burger Temp", "option_name": "Medium Rare"},
                        ]
                    }
                ],
            }
        ]
        actual = [
            {
                "item_name": "Combo Meal",
                "selection_paths": [
                    {
                        "path": [
                            {"group_name": "Entree", "option_name": "Burger"},
                            {"group_name": "Burger Temp", "option_name": "Medium Rare"},
                        ]
                    }
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        assert all(d.matched for d in results)

    def test_two_step_path_second_step_mismatch(self) -> None:
        expected = [
            {
                "item_name": "Combo Meal",
                "selection_paths": [
                    {
                        "path": [
                            {"group_name": "Entree", "option_name": "Burger"},
                            {"group_name": "Burger Temp", "option_name": "Medium Rare"},
                        ]
                    }
                ],
            }
        ]
        actual = [
            {
                "item_name": "Combo Meal",
                "selection_paths": [
                    {
                        "path": [
                            {"group_name": "Entree", "option_name": "Burger"},
                            {"group_name": "Burger Temp", "option_name": "Well Done"},
                        ]
                    }
                ],
            }
        ]
        results = _toast._compare_items(expected, actual)
        failed = [d for d in results if not d.matched]
        assert len(failed) == 1
        assert "option_name" in failed[0].field_path
        assert "Well Done" in failed[0].detail

    def test_path_step_count_mismatch(self) -> None:
        """Expected has 2 steps, actual has 1 — should report path count mismatch."""
        paths_expected = [
            {
                "path": [
                    {"group_name": "Entree", "option_name": "Burger"},
                    {"group_name": "Burger Temp", "option_name": "Rare"},
                ]
            }
        ]
        paths_actual = [{"path": [{"group_name": "Entree", "option_name": "Burger"}]}]
        results = _toast._compare_selection_paths(
            paths_expected, paths_actual, "items[0]"
        )
        failed = [d for d in results if not d.matched]
        assert len(failed) == 1
        assert "count mismatch" in failed[0].detail


# ---------------------------------------------------------------------------
# Hard: complex full-order scenarios (end-to-end)
# ---------------------------------------------------------------------------


class TestComplexEndToEnd:
    """Full evaluate_tool_call_args with realistic multi-item, multi-modifier orders."""

    def test_full_order_with_modifiers_and_notes(self) -> None:
        """Two items: one with selection_paths, one with item_note."""
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "customer": {
                        "first_name": "Sam",
                        "last_name": "Rivera",
                        "phone": "5557778888",
                    },
                    "items": [
                        {
                            "item_name": "Stuffed DD Chicago Classic",
                            "quantity": 1,
                            "selection_paths": [
                                {
                                    "path": [
                                        {
                                            "group_name": "Size",
                                            "option_name": "Medium",
                                        }
                                    ]
                                },
                                {
                                    "path": [
                                        {
                                            "group_name": "Sauce/Cheese Options",
                                            "option_name": "Light Cheese",
                                        }
                                    ]
                                },
                            ],
                        },
                        {
                            "item_name": "Garlic Bread",
                            "quantity": 2,
                            "item_note": "extra crispy",
                        },
                    ],
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {
                        "customer": {
                            "first_name": "Sam",
                            "last_name": "Rivera",
                            "phone": "(555) 777-8888",
                        },
                        "items": [
                            {
                                "item_name": "Stuffed DD Chicago Classic",
                                "quantity": 1,
                                "selection_paths": [
                                    {
                                        "path": [
                                            {
                                                "group_name": "Sauce/Cheese Options",
                                                "option_name": "Light Cheese",
                                            }
                                        ]
                                    },
                                    {
                                        "path": [
                                            {
                                                "group_name": "Size",
                                                "option_name": "Medium",
                                            }
                                        ]
                                    },
                                ],
                            },
                            {
                                "item_name": "Garlic Bread",
                                "quantity": 2,
                                "item_note": "extra crispy",
                            },
                        ],
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0

    def test_full_order_multiple_failures(self) -> None:
        """Wrong quantity, wrong item_note, wrong selection — score reflects all."""
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "customer": {"first_name": "Alex", "phone": "5551112222"},
                    "items": [
                        {
                            "item_name": "Wings",
                            "quantity": 10,
                            "item_note": "extra sauce",
                            "selection_paths": [
                                {
                                    "path": [
                                        {
                                            "group_name": "Wing Sauce",
                                            "option_name": "BBQ",
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {
                        "customer": {"first_name": "Alex", "phone": "5551112222"},
                        "items": [
                            {
                                "item_name": "Wings",
                                "quantity": 5,
                                "item_note": "no sauce",
                                "selection_paths": [
                                    {
                                        "path": [
                                            {
                                                "group_name": "Wing Sauce",
                                                "option_name": "Ranch",
                                            }
                                        ]
                                    }
                                ],
                            }
                        ],
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is False
        assert result.raw_output is not None
        details = result.raw_output["match_details"]
        failed_fields = {d["field"] for d in details if not d["matched"]}
        # quantity, item_note, and option_name should all fail
        assert any("quantity" in f for f in failed_fields)
        assert any("item_note" in f for f in failed_fields)
        assert any("option_name" in f for f in failed_fields)
        # customer(first_name, phone) + item_name + group_name = 4 of 7 total
        matched_count = sum(1 for d in details if d["matched"])
        assert matched_count == 4

    def test_phone_with_country_code(self) -> None:
        """Phone with +1 prefix should normalize to same digits."""
        expected = {"customer": {"phone": "15551234567"}}
        actual = {"customer": {"phone": "+1 (555) 123-4567"}}
        results = _toast.evaluate(expected, actual)
        phone_result = [d for d in results if d.field_path == "customer.phone"]
        assert phone_result[0].matched is True

    def test_actual_missing_customer_fields(self) -> None:
        """Actual has no customer sub-fields — all expected fields fail."""
        expected = {
            "customer": {
                "first_name": "John",
                "last_name": "Doe",
                "phone": "5551234567",
            }
        }
        actual = {"customer": {}}
        results = _toast.evaluate(expected, actual)
        assert len(results) == 3
        assert all(not d.matched for d in results)

    def test_actual_missing_items_array(self) -> None:
        """Expected has items but actual has none — count mismatch."""
        expected = {
            "items": [
                {"item_name": "Pizza", "quantity": 1},
                {"item_name": "Salad", "quantity": 1},
            ]
        }
        actual: dict[str, list[object]] = {"items": []}
        results = _toast.evaluate(expected, actual)
        assert len(results) == 1
        assert results[0].matched is False
        assert "count mismatch" in results[0].detail

    def test_extra_actual_items_ignored_when_counts_match(self) -> None:
        """Extra fields in actual items don't affect matching."""
        expected = [{"item_name": "Pizza", "quantity": 1}]
        actual = [
            {
                "item_name": "Pizza",
                "quantity": 1,
                "extra_field": "ignored",
                "price": 12.99,
            }
        ]
        results = _toast._compare_items(expected, actual)
        assert all(d.matched for d in results)

    def test_score_granularity_many_fields(self) -> None:
        """Verify score precision with many fields — 9 match, 1 fails = 0.9."""
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {
                    "customer": {
                        "first_name": "A",
                        "last_name": "B",
                        "phone": "1234567890",
                    },
                    "items": [
                        {
                            "item_name": "Item1",
                            "quantity": 1,
                            "item_note": "note1",
                            "selection_paths": [
                                {
                                    "path": [
                                        {
                                            "group_name": "G1",
                                            "option_name": "O1",
                                        }
                                    ]
                                }
                            ],
                        },
                        {"item_name": "Item2", "quantity": 2},
                    ],
                },
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {
                        "customer": {
                            "first_name": "A",
                            "last_name": "B",
                            "phone": "1234567890",
                        },
                        "items": [
                            {
                                "item_name": "Item1",
                                "quantity": 1,
                                "item_note": "note1",
                                "selection_paths": [
                                    {
                                        "path": [
                                            {
                                                "group_name": "G1",
                                                "option_name": "O1",
                                            }
                                        ]
                                    }
                                ],
                            },
                            {"item_name": "Item2", "quantity": 999},
                        ],
                    },
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is False
        # 10 total fields: 3 customer + item0(name,qty,note,group,option) + item1(name,qty)
        # Only item1.quantity fails → 9/10
        assert result.score == 0.9


# ---------------------------------------------------------------------------
# Class-based architecture
# ---------------------------------------------------------------------------


class TestEvaluatorRegistry:
    def test_toast_prefix_returns_toast_evaluator(self) -> None:
        evaluator = _get_evaluator("toast.validate_order_intent")
        assert isinstance(evaluator, ToastArgumentEvaluator)

    def test_toast_other_tool_returns_toast_evaluator(self) -> None:
        evaluator = _get_evaluator("toast.submit_order")
        assert isinstance(evaluator, ToastArgumentEvaluator)

    def test_checkout_order_returns_toast_evaluator(self) -> None:
        evaluator = _get_evaluator("checkout_order")
        assert isinstance(evaluator, ToastArgumentEvaluator)

    def test_unknown_tool_returns_none(self) -> None:
        assert _get_evaluator("unknown.some_tool") is None

    def test_empty_tool_name_returns_none(self) -> None:
        assert _get_evaluator("") is None

    def test_unsupported_tool_fails_in_evaluate(self) -> None:
        """Non-Toast tool with args should fail, not silently pass."""
        expected = [{"tool": "unknown.do_thing", "args": {"key": "value"}}]
        actual = [
            {
                "payload": {
                    "tool_name": "unknown.do_thing",
                    "arguments": {"key": "value"},
                }
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is False
        assert result.raw_output is not None
        assert (
            result.raw_output["match_details"][0]["detail"] == "unsupported tool family"
        )


class TestToastEvaluatorDirectly:
    """Call ToastArgumentEvaluator.evaluate() directly."""

    def test_evaluate_returns_match_details(self) -> None:
        evaluator = ToastArgumentEvaluator()
        expected = {
            "customer": {"first_name": "John", "phone": "(555) 999-0000"},
            "items": [{"item_name": "Pizza", "quantity": 1}],
        }
        actual = {
            "customer": {"first_name": "John", "phone": "5559990000"},
            "items": [{"item_name": "Pizza", "quantity": 1}],
        }
        results = evaluator.evaluate(expected, actual)
        assert all(d.matched for d in results)
        field_paths = {d.field_path for d in results}
        assert "customer.first_name" in field_paths
        assert "customer.phone" in field_paths
        assert "items[0].item_name" in field_paths
        assert "items[0].quantity" in field_paths

    def test_base_class_normalize_text(self) -> None:
        evaluator = ToastArgumentEvaluator()
        assert evaluator._normalize_text("hello   world") == "hello world"
        assert evaluator._normalize_text(42) == 42

    def test_base_class_compare_named_value(self) -> None:
        evaluator = ToastArgumentEvaluator()
        result = evaluator._compare_named_value(
            field_path="test.field", expected="hello  world", actual="hello world"
        )
        assert result.matched is True


class TestDispatchInEvaluateToolCallArgs:
    """Verify evaluate_tool_call_args dispatches to the correct evaluator."""

    def test_toast_tool_uses_toast_evaluator(self) -> None:
        """Toast tools get phone normalization — proves dispatch works."""
        expected = [
            {
                "tool": "toast.validate_order_intent",
                "args": {"customer": {"phone": "5551234567"}},
            }
        ]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "toast.validate_order_intent",
                    "arguments": {"customer": {"phone": "(555) 123-4567"}},
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0


# ---------------------------------------------------------------------------
# Payload-wrapped tool calls (DB event structure)
# ---------------------------------------------------------------------------


class TestPayloadWrappedToolCalls:
    """Tool calls stored as {type, payload: {tool_name}} are unwrapped."""

    def test_payload_wrapped_name_only(self) -> None:
        expected = [{"tool": "checkout_order", "args": {}}]
        actual = [
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "checkout_order",
                    "arguments": {"customer": {"first_name": "John"}},
                },
            }
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.score == 1.0

    def test_payload_wrapped_with_unexpected(self) -> None:
        expected = [{"tool": "checkout_order", "args": {}}]
        actual = [
            {
                "type": "tool_call",
                "payload": {"tool_name": "checkout_order", "arguments": {}},
            },
            {
                "type": "tool_call",
                "payload": {
                    "tool_name": "get_toast_item_details_v3",
                    "arguments": {},
                },
            },
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.raw_output is not None
        assert "get_toast_item_details_v3" in result.raw_output["unexpected_tools"]


# ---------------------------------------------------------------------------
# Unexpected tools reporting
# ---------------------------------------------------------------------------


class TestUnexpectedTools:
    def test_unexpected_tools_reported_in_raw_output(self) -> None:
        expected = [{"tool": "checkout_order", "args": {}}]
        actual = [
            {"tool_name": "checkout_order"},
            {"tool_name": "get_menu_inventory_tool"},
        ]
        result = evaluate_tool_call_args(expected, actual)
        assert result.passed is True
        assert result.raw_output is not None
        assert "get_menu_inventory_tool" in result.raw_output["unexpected_tools"]
        assert "Unexpected tools" in result.reason

    def test_no_unexpected_when_all_matched(self) -> None:
        expected = [{"tool": "checkout_order", "args": {}}]
        actual = [{"tool_name": "checkout_order"}]
        result = evaluate_tool_call_args(expected, actual)
        assert result.raw_output is not None
        assert result.raw_output["unexpected_tools"] == []
