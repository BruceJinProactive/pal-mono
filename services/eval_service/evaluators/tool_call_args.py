"""Unified tool call evaluator: name verification + argument validation.

Deterministic comparison of expected vs actual tool calls.

Uses a class-based dispatch model for argument matching:
    ToolArgumentEvaluator (ABC)
    └── ToastArgumentEvaluator  — customer/items/selection_paths matching

Produces metric ``tool_call_accuracy`` with per-field ``MatchDetail`` in
``raw_output`` for debugging.  Missing/unexpected tool names are reported
alongside argument-level details.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services.eval_service._evaluators import EvaluatorResult

# ---------------------------------------------------------------------------
# MatchDetail
# ---------------------------------------------------------------------------


@dataclass
class MatchDetail:
    """Per-field comparison result."""

    field_path: str
    matched: bool
    detail: str


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class ToolArgumentEvaluator(ABC):
    """Abstract base for tool-specific argument comparison."""

    @abstractmethod
    def evaluate(
        self, expected_args: dict[str, Any], actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        """Compare expected vs actual arguments, return per-field results."""

    # -- shared helpers available to all subclasses --

    @staticmethod
    def _get_aliased(d: dict[str, Any], *keys: str) -> Any:
        """Return the first non-None value found for the given keys."""
        for k in keys:
            val = d.get(k)
            if val is not None:
                return val
        return None

    def _normalize_text(self, value: Any) -> Any:
        """Collapse whitespace, strip. Non-strings pass through unchanged."""
        if not isinstance(value, str):
            return value
        return re.sub(r"\s+", " ", value).strip()

    def _compare_named_value(
        self,
        *,
        field_path: str,
        expected: Any,
        actual: Any,
    ) -> MatchDetail:
        """Compare two values using whitespace-normalized string matching."""
        if self._normalize_text(expected) != self._normalize_text(actual):
            return MatchDetail(
                field_path, False, f"expected {expected!r}, got {actual!r}"
            )
        return MatchDetail(field_path, True, f"{actual!r}")


# ---------------------------------------------------------------------------
# Toast evaluator
# ---------------------------------------------------------------------------


class ToastArgumentEvaluator(ToolArgumentEvaluator):
    """Argument evaluator for ``toast.*`` tool calls.

    Compares customer fields (with phone normalization) and items
    (with whitespace-normalized text and selection_path canonical matching).
    """

    def evaluate(
        self, expected_args: dict[str, Any], actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        # Customer fields
        exp_customer = expected_args.get("customer", {})
        act_customer = actual_args.get("customer", {})

        # Support both snake_case (YAML scenarios) and camelCase (Toast runtime)
        _CUSTOMER_KEY_ALIASES: dict[str, str] = {
            "firstName": "first_name",
            "lastName": "last_name",
        }
        act_customer = {
            _CUSTOMER_KEY_ALIASES.get(k, k): v for k, v in act_customer.items()
        }

        for field in ["first_name", "last_name"]:
            exp_val = exp_customer.get(field)
            if exp_val is not None:
                act_val = act_customer.get(field)
                results.append(
                    self._compare_named_value(
                        field_path=f"customer.{field}",
                        expected=exp_val,
                        actual=act_val,
                    )
                )

        # Phone (digits-only normalization)
        exp_phone = self._normalize_phone(exp_customer.get("phone"))
        act_phone = self._normalize_phone(act_customer.get("phone"))
        if exp_phone is not None:
            if exp_phone != act_phone:
                results.append(
                    MatchDetail(
                        "customer.phone",
                        False,
                        f"expected {exp_phone!r}, got {act_phone!r}",
                    )
                )
            else:
                results.append(MatchDetail("customer.phone", True, f"{act_phone!r}"))

        # Items
        exp_items = expected_args.get("items", [])
        act_items = actual_args.get("items", [])
        results.extend(self._compare_items(exp_items, act_items))

        return results

    # -- Toast-specific helpers --

    @staticmethod
    def _normalize_phone(phone: str | None) -> str | None:
        """Strip non-digits: ``(555) 123-4567`` -> ``5551234567``."""
        if phone is None:
            return None
        return re.sub(r"\D", "", phone)

    def _compare_items(
        self,
        expected_items: list[dict[str, Any]],
        actual_items: list[dict[str, Any]],
    ) -> list[MatchDetail]:
        """Compare ``items`` arrays for Toast tool intent."""
        results: list[MatchDetail] = []

        if len(expected_items) != len(actual_items):
            results.append(
                MatchDetail(
                    "items",
                    False,
                    f"count mismatch: expected {len(expected_items)}, got {len(actual_items)}",
                )
            )
            return results

        for i, (exp_item, act_item) in enumerate(
            zip(expected_items, actual_items, strict=True)
        ):
            item_path = f"items[{i}]"

            # item_name
            results.append(
                self._compare_named_value(
                    field_path=f"{item_path}.item_name",
                    expected=exp_item.get("item_name"),
                    actual=act_item.get("item_name"),
                )
            )

            # quantity
            exp_qty = exp_item.get("quantity")
            act_qty = act_item.get("quantity")
            if exp_qty is not None:
                if exp_qty != act_qty:
                    results.append(
                        MatchDetail(
                            f"{item_path}.quantity",
                            False,
                            f"expected {exp_qty}, got {act_qty}",
                        )
                    )
                else:
                    results.append(
                        MatchDetail(f"{item_path}.quantity", True, f"{act_qty}")
                    )

            # item_note (only if present in expected)
            exp_note = exp_item.get("item_note")
            if exp_note is not None:
                results.append(
                    self._compare_named_value(
                        field_path=f"{item_path}.item_note",
                        expected=exp_note,
                        actual=act_item.get("item_note"),
                    )
                )

            # selection_paths
            exp_paths = exp_item.get("selection_paths", [])
            act_paths = act_item.get("selection_paths", [])
            if exp_paths or act_paths:
                results.extend(
                    self._compare_selection_paths(exp_paths, act_paths, item_path)
                )

        return results

    def _canonicalize_selection_path(
        self,
        selection_path: dict[str, Any],
    ) -> tuple[tuple[Any, Any], ...]:
        """Convert one selection path into a comparable canonical tuple."""
        path_items = selection_path.get("path", [])
        return tuple(
            (
                self._normalize_text(item.get("group_name")),
                self._normalize_text(item.get("option_name")),
            )
            for item in path_items
        )

    def _selection_path_match_score(
        self,
        expected_path_items: list[dict[str, Any]],
        actual_path_items: list[dict[str, Any]],
    ) -> int:
        """Rough similarity score for mismatch diagnostics."""
        score = 0
        if len(expected_path_items) == len(actual_path_items):
            score += 1
        for exp_item, act_item in zip(
            expected_path_items, actual_path_items, strict=False
        ):
            if self._normalize_text(exp_item.get("group_name")) == self._normalize_text(
                act_item.get("group_name")
            ):
                score += 1
            if self._normalize_text(
                exp_item.get("option_name")
            ) == self._normalize_text(act_item.get("option_name")):
                score += 1
        return score

    def _compare_single_selection_path(
        self,
        expected_path_items: list[dict[str, Any]],
        actual_path_items: list[dict[str, Any]],
        selection_path_loc: str,
    ) -> list[MatchDetail]:
        """Compare one selection path after expected/actual matching is decided."""
        results: list[MatchDetail] = []

        if len(expected_path_items) != len(actual_path_items):
            results.append(
                MatchDetail(
                    f"{selection_path_loc}.path",
                    False,
                    f"count mismatch: expected {len(expected_path_items)}, got {len(actual_path_items)}",
                )
            )
            return results

        for index, (exp_item, act_item) in enumerate(
            zip(expected_path_items, actual_path_items, strict=True)
        ):
            loc = f"{selection_path_loc}.path[{index}]"
            results.append(
                self._compare_named_value(
                    field_path=f"{loc}.group_name",
                    expected=exp_item.get("group_name"),
                    actual=act_item.get("group_name"),
                )
            )
            results.append(
                self._compare_named_value(
                    field_path=f"{loc}.option_name",
                    expected=exp_item.get("option_name"),
                    actual=act_item.get("option_name"),
                )
            )

        return results

    def _compare_selection_paths(
        self,
        expected_paths: list[dict[str, Any]],
        actual_paths: list[dict[str, Any]],
        item_path: str,
    ) -> list[MatchDetail]:
        """Compare ``selection_paths`` arrays.

        Each selection_path has a ``path`` array of ``{group_name, option_name}``
        objects.  Matching uses canonical tuple comparison for order-independence.
        """
        results: list[MatchDetail] = []

        if len(expected_paths) != len(actual_paths):
            results.append(
                MatchDetail(
                    f"{item_path}.selection_paths",
                    False,
                    f"count mismatch: expected {len(expected_paths)}, got {len(actual_paths)}",
                )
            )
            return results

        remaining_actual: list[tuple[int, dict[str, Any]]] = list(
            enumerate(actual_paths)
        )

        for exp_idx, exp_sp in enumerate(expected_paths):
            sp_loc = f"{item_path}.selection_paths[{exp_idx}]"
            exp_key = self._canonicalize_selection_path(exp_sp)
            matched_idx: int | None = None

            for rem_idx, (_, act_sp) in enumerate(remaining_actual):
                if self._canonicalize_selection_path(act_sp) == exp_key:
                    matched_idx = rem_idx
                    break

            if matched_idx is None:
                if not remaining_actual:
                    results.append(MatchDetail(sp_loc, False, "missing selection_path"))
                    continue
                matched_idx = max(
                    range(len(remaining_actual)),
                    key=lambda i: self._selection_path_match_score(
                        exp_sp.get("path", []),
                        remaining_actual[i][1].get("path", []),
                    ),
                )

            _, act_sp = remaining_actual.pop(matched_idx)
            results.extend(
                self._compare_single_selection_path(
                    expected_path_items=exp_sp.get("path", []),
                    actual_path_items=act_sp.get("path", []),
                    selection_path_loc=sp_loc,
                )
            )

        for actual_idx, _ in remaining_actual:
            results.append(
                MatchDetail(
                    f"{item_path}.selection_paths[{actual_idx}]",
                    False,
                    "unexpected selection_path",
                )
            )

        return results


# ---------------------------------------------------------------------------
# Evaluator registry
# ---------------------------------------------------------------------------

_EVALUATOR_REGISTRY: dict[str, type[ToolArgumentEvaluator]] = {
    "toast.": ToastArgumentEvaluator,
    "checkout_order": ToastArgumentEvaluator,
}


def _get_evaluator(tool_name: str) -> ToolArgumentEvaluator | None:
    """Return an evaluator instance for the given tool name, or None if unsupported.

    Matches by exact name first, then by prefix.
    """
    if tool_name in _EVALUATOR_REGISTRY:
        return _EVALUATOR_REGISTRY[tool_name]()
    for prefix, cls in _EVALUATOR_REGISTRY.items():
        if tool_name.startswith(prefix):
            return cls()
    return None


# ---------------------------------------------------------------------------
# Actual arg extraction from our event structure
# ---------------------------------------------------------------------------


def _extract_tool_name(tc: Mapping[str, Any]) -> str:
    """Return the tool name from either event-payload or flat structure."""
    payload = tc.get("payload", {})
    name = payload.get("tool_name", "")
    if name:
        return str(name)
    return str(tc.get("tool_name") or tc.get("tool", ""))


def _extract_args(tc: Mapping[str, Any]) -> dict[str, Any]:
    """Return arguments dict from either event-payload or flat structure."""
    payload = tc.get("payload", {})
    if payload.get("tool_name"):
        return dict(payload.get("arguments", {}))
    return dict(tc.get("args", tc.get("arguments", {})))


# ---------------------------------------------------------------------------
# Evaluator entry point
# ---------------------------------------------------------------------------


def evaluate_tool_call_args(
    expected_tool_calls: Sequence[Mapping[str, Any]],
    actual_tool_calls: Sequence[Mapping[str, Any]],
) -> EvaluatorResult:
    """Unified tool call verification: name matching + argument validation.

    For each expected tool call:
    1. Verify the tool was actually called (name match).
    2. If args are specified and a matching evaluator exists, compare arguments.

    Also reports unexpected tool calls (called but not expected).

    Score = matched_fields / total_fields, passed when score >= 1.0.
    Per-field details are returned in ``raw_output["match_details"]``.
    """
    if not expected_tool_calls:
        return EvaluatorResult(
            metric_name="tool_call_accuracy",
            score=1.0,
            passed=True,
            reason="No tool calls expected",
        )

    all_details: list[MatchDetail] = []
    actual_names = [_extract_tool_name(tc) for tc in actual_tool_calls]
    matched_actual_indices: set[int] = set()

    for exp_tc in expected_tool_calls:
        tool_name = str(exp_tc.get("tool", ""))
        exp_args = exp_tc.get("args", {})

        # Find the first unmatched actual call with the same tool name
        found_idx: int | None = None
        for i, name in enumerate(actual_names):
            if name == tool_name and i not in matched_actual_indices:
                found_idx = i
                break

        if found_idx is None:
            all_details.append(
                MatchDetail(tool_name, False, "expected tool not called")
            )
            continue

        matched_actual_indices.add(found_idx)

        # Tool name matched
        if not exp_args:
            all_details.append(
                MatchDetail(tool_name, True, "tool called (no arg check)")
            )
            continue

        evaluator = _get_evaluator(tool_name)
        if evaluator is None:
            all_details.append(MatchDetail(tool_name, False, "unsupported tool family"))
            continue

        act_args = _extract_args(actual_tool_calls[found_idx])
        all_details.extend(evaluator.evaluate(exp_args, act_args))

    # Report unexpected tool calls
    unexpected_names = [
        actual_names[i]
        for i in range(len(actual_names))
        if i not in matched_actual_indices and actual_names[i]
    ]

    matched = sum(1 for d in all_details if d.matched)
    total = len(all_details)
    score = matched / total if total > 0 else 1.0

    parts: list[str] = [f"Matched {matched}/{total} fields."]
    if unexpected_names:
        parts.append(f"Unexpected tools: {unexpected_names}")

    return EvaluatorResult(
        metric_name="tool_call_accuracy",
        score=score,
        passed=score >= 1.0,
        reason=" ".join(parts),
        raw_output={
            "match_details": [
                {"field": d.field_path, "matched": d.matched, "detail": d.detail}
                for d in all_details
            ],
            "unexpected_tools": unexpected_names,
            "score": score,
        },
    )
