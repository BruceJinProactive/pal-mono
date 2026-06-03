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
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services.eval_service._evaluators import EvaluatorResult

MISSING = object()

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


class LookupArgumentEvaluator(ToolArgumentEvaluator):
    """Argument evaluator for ``get_toast_item_details_v3`` lookup calls.

    Compares the ``items`` array: item_name matching + order-independent
    target comparison (group_name + path_prefix).
    """

    def evaluate(
        self, expected_args: dict[str, Any], actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []
        exp_items = expected_args.get("items", [])
        act_items = actual_args.get("items", [])
        results.extend(self._compare_lookup_items(exp_items, act_items))
        return results

    def _compare_lookup_items(
        self,
        expected_items: list[dict[str, Any]],
        actual_items: list[dict[str, Any]],
    ) -> list[MatchDetail]:
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

        remaining_actual: list[tuple[int, dict[str, Any]]] = list(
            enumerate(actual_items)
        )

        for exp_idx, exp_item in enumerate(expected_items):
            item_path = f"items[{exp_idx}]"
            exp_name = self._normalize_text(exp_item.get("item_name"))

            # Find best matching actual item by item_name
            matched_idx: int | None = None
            for rem_idx, (_, act_item) in enumerate(remaining_actual):
                if self._normalize_text(act_item.get("item_name")) == exp_name:
                    matched_idx = rem_idx
                    break

            if matched_idx is None:
                results.append(
                    MatchDetail(
                        f"{item_path}.item_name",
                        False,
                        f"expected {exp_name!r}, not found in actual items",
                    )
                )
                continue

            _, act_item = remaining_actual.pop(matched_idx)

            results.append(
                self._compare_named_value(
                    field_path=f"{item_path}.item_name",
                    expected=exp_item.get("item_name"),
                    actual=act_item.get("item_name"),
                )
            )

            exp_targets = exp_item.get("targets", [])
            act_targets = act_item.get("targets", [])
            if exp_targets or act_targets:
                results.extend(
                    self._compare_targets(exp_targets, act_targets, item_path)
                )

        return results

    def _canonicalize_target(
        self, target: dict[str, Any]
    ) -> tuple[Any, tuple[tuple[Any, Any], ...]]:
        """Canonical form: (group_name, ((pfx_group, pfx_option), ...))."""
        group = self._normalize_text(target.get("group_name"))
        prefix_items = target.get("path_prefix", [])
        prefix_key = tuple(
            (
                self._normalize_text(p.get("group_name")),
                self._normalize_text(p.get("option_name")),
            )
            for p in prefix_items
        )
        return (group, prefix_key)

    def _compare_targets(
        self,
        expected_targets: list[dict[str, Any]],
        actual_targets: list[dict[str, Any]],
        item_path: str,
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        if len(expected_targets) != len(actual_targets):
            results.append(
                MatchDetail(
                    f"{item_path}.targets",
                    False,
                    f"count mismatch: expected {len(expected_targets)}, got {len(actual_targets)}",
                )
            )
            return results

        remaining_actual: list[tuple[int, dict[str, Any]]] = list(
            enumerate(actual_targets)
        )

        for exp_idx, exp_tgt in enumerate(expected_targets):
            tgt_path = f"{item_path}.targets[{exp_idx}]"
            exp_key = self._canonicalize_target(exp_tgt)
            matched_idx: int | None = None

            for rem_idx, (_, act_tgt) in enumerate(remaining_actual):
                if self._canonicalize_target(act_tgt) == exp_key:
                    matched_idx = rem_idx
                    break

            if matched_idx is None:
                if not remaining_actual:
                    results.append(MatchDetail(tgt_path, False, "missing target"))
                    continue
                # Pick best match for diagnostics
                matched_idx = 0

            _, act_tgt = remaining_actual.pop(matched_idx)

            results.append(
                self._compare_named_value(
                    field_path=f"{tgt_path}.group_name",
                    expected=exp_tgt.get("group_name"),
                    actual=act_tgt.get("group_name"),
                )
            )

            exp_prefix = exp_tgt.get("path_prefix", [])
            act_prefix = act_tgt.get("path_prefix", [])
            if exp_prefix or act_prefix:
                results.extend(
                    self._compare_path_prefix(exp_prefix, act_prefix, tgt_path)
                )

        return results

    def _compare_path_prefix(
        self,
        expected_prefix: list[dict[str, Any]],
        actual_prefix: list[dict[str, Any]],
        tgt_path: str,
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        if len(expected_prefix) != len(actual_prefix):
            results.append(
                MatchDetail(
                    f"{tgt_path}.path_prefix",
                    False,
                    f"count mismatch: expected {len(expected_prefix)}, got {len(actual_prefix)}",
                )
            )
            return results

        for i, (exp_step, act_step) in enumerate(
            zip(expected_prefix, actual_prefix, strict=True)
        ):
            loc = f"{tgt_path}.path_prefix[{i}]"
            results.append(
                self._compare_named_value(
                    field_path=f"{loc}.group_name",
                    expected=exp_step.get("group_name"),
                    actual=act_step.get("group_name"),
                )
            )
            results.append(
                self._compare_named_value(
                    field_path=f"{loc}.option_name",
                    expected=exp_step.get("option_name"),
                    actual=act_step.get("option_name"),
                )
            )

        return results


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


class OloLookupArgumentEvaluator(ToolArgumentEvaluator):
    """Argument evaluator for ``lookup_olo_order_options_v1`` calls.

    Olo lookup uses ``queries`` instead of Toast's ``items`` shape.  Queries can
    start from ``item_name`` or continue from ``item_handle``; targets compare
    group, option, and nested path-prefix context.
    """

    def evaluate(
        self, expected_args: dict[str, Any], actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        return self._compare_queries(
            expected_args.get("queries", []),
            actual_args.get("queries", []),
        )

    def _compare_queries(
        self,
        expected_queries: list[dict[str, Any]],
        actual_queries: list[dict[str, Any]],
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        if len(expected_queries) != len(actual_queries):
            results.append(
                MatchDetail(
                    "queries",
                    False,
                    f"count mismatch: expected {len(expected_queries)}, got {len(actual_queries)}",
                )
            )
            return results

        remaining_actual: list[tuple[int, dict[str, Any]]] = list(
            enumerate(actual_queries)
        )

        for exp_idx, exp_query in enumerate(expected_queries):
            query_path = f"queries[{exp_idx}]"
            matched_idx = self._find_matching_query(exp_query, remaining_actual)

            if matched_idx is None:
                results.append(
                    MatchDetail(
                        query_path,
                        False,
                        f"expected query {self._query_key(exp_query)!r}, not found",
                    )
                )
                continue

            _, act_query = remaining_actual.pop(matched_idx)

            if exp_query.get("item_handle") is not None:
                results.append(
                    self._compare_named_value(
                        field_path=f"{query_path}.item_handle",
                        expected=exp_query.get("item_handle"),
                        actual=act_query.get("item_handle"),
                    )
                )
            if exp_query.get("item_name") is not None:
                results.append(
                    self._compare_named_value(
                        field_path=f"{query_path}.item_name",
                        expected=exp_query.get("item_name"),
                        actual=act_query.get("item_name"),
                    )
                )

            exp_targets = exp_query.get("targets", [])
            act_targets = act_query.get("targets", [])
            if exp_targets or act_targets:
                results.extend(
                    self._compare_targets(exp_targets, act_targets, query_path)
                )

        return results

    def _query_key(self, query: dict[str, Any]) -> tuple[str, Any]:
        item_handle = query.get("item_handle")
        if item_handle is not None:
            return ("item_handle", item_handle)
        return ("item_name", self._normalize_text(query.get("item_name")))

    def _find_matching_query(
        self,
        expected_query: dict[str, Any],
        remaining_actual: list[tuple[int, dict[str, Any]]],
    ) -> int | None:
        expected_key = self._query_key(expected_query)
        for rem_idx, (_, actual_query) in enumerate(remaining_actual):
            if self._query_key(actual_query) == expected_key:
                return rem_idx
        return None

    def _canonicalize_target(
        self, target: dict[str, Any]
    ) -> tuple[Any, Any, tuple[tuple[Any, Any], ...]]:
        prefix_items = target.get("path_prefix", [])
        prefix_key = tuple(
            (
                self._normalize_text(step.get("group_name")),
                self._normalize_text(step.get("option_name")),
            )
            for step in prefix_items
        )
        return (
            self._normalize_text(target.get("group_name")),
            self._normalize_text(target.get("option_name")),
            prefix_key,
        )

    def _compare_targets(
        self,
        expected_targets: list[dict[str, Any]],
        actual_targets: list[dict[str, Any]],
        query_path: str,
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        if len(expected_targets) != len(actual_targets):
            results.append(
                MatchDetail(
                    f"{query_path}.targets",
                    False,
                    f"count mismatch: expected {len(expected_targets)}, got {len(actual_targets)}",
                )
            )
            return results

        remaining_actual: list[tuple[int, dict[str, Any]]] = list(
            enumerate(actual_targets)
        )

        for exp_idx, exp_target in enumerate(expected_targets):
            target_path = f"{query_path}.targets[{exp_idx}]"
            expected_key = self._canonicalize_target(exp_target)
            matched_idx: int | None = None

            for rem_idx, (_, actual_target) in enumerate(remaining_actual):
                if self._canonicalize_target(actual_target) == expected_key:
                    matched_idx = rem_idx
                    break

            if matched_idx is None:
                if not remaining_actual:
                    results.append(MatchDetail(target_path, False, "missing target"))
                    continue
                matched_idx = 0

            _, actual_target = remaining_actual.pop(matched_idx)
            results.extend(
                self._compare_single_target(
                    exp_target,
                    actual_target,
                    target_path,
                )
            )

        return results

    def _compare_single_target(
        self,
        expected_target: dict[str, Any],
        actual_target: dict[str, Any],
        target_path: str,
    ) -> list[MatchDetail]:
        results = [
            self._compare_named_value(
                field_path=f"{target_path}.group_name",
                expected=expected_target.get("group_name"),
                actual=actual_target.get("group_name"),
            )
        ]

        if expected_target.get("option_name") is not None:
            results.append(
                self._compare_named_value(
                    field_path=f"{target_path}.option_name",
                    expected=expected_target.get("option_name"),
                    actual=actual_target.get("option_name"),
                )
            )

        expected_prefix = expected_target.get("path_prefix", [])
        actual_prefix = actual_target.get("path_prefix", [])
        if expected_prefix or actual_prefix:
            results.extend(
                self._compare_path_prefix(expected_prefix, actual_prefix, target_path)
            )

        return results

    def _compare_path_prefix(
        self,
        expected_prefix: list[dict[str, Any]],
        actual_prefix: list[dict[str, Any]],
        target_path: str,
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        if len(expected_prefix) != len(actual_prefix):
            results.append(
                MatchDetail(
                    f"{target_path}.path_prefix",
                    False,
                    f"count mismatch: expected {len(expected_prefix)}, got {len(actual_prefix)}",
                )
            )
            return results

        for index, (expected_step, actual_step) in enumerate(
            zip(expected_prefix, actual_prefix, strict=True)
        ):
            step_path = f"{target_path}.path_prefix[{index}]"
            results.append(
                self._compare_named_value(
                    field_path=f"{step_path}.group_name",
                    expected=expected_step.get("group_name"),
                    actual=actual_step.get("group_name"),
                )
            )
            results.append(
                self._compare_named_value(
                    field_path=f"{step_path}.option_name",
                    expected=expected_step.get("option_name"),
                    actual=actual_step.get("option_name"),
                )
            )

        return results


class OloOrderArgumentEvaluator(ToolArgumentEvaluator):
    """Argument evaluator for ``olo_create_order_v1`` handle-backed calls."""

    FORBIDDEN_ID_KEYS = {
        "productid",
        "choiceid",
        "chainproductid",
        "chainchoiceid",
    }

    def evaluate(
        self, expected_args: dict[str, Any], actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []
        results.extend(self._validate_model_facing_shape(actual_args))

        exp_handoff = expected_args.get("handoff_mode")
        act_handoff = actual_args.get("handoff_mode")
        if act_handoff is None:
            results.append(
                MatchDetail(
                    "handoff_mode",
                    False,
                    "Olo create-order calls must include handoff_mode",
                )
            )
        elif exp_handoff is not None:
            results.append(
                self._compare_named_value(
                    field_path="handoff_mode",
                    expected=exp_handoff,
                    actual=act_handoff,
                )
            )

        results.extend(
            self._compare_customer(
                expected_args.get("customer", {}),
                actual_args.get("customer", {}),
            )
        )
        results.extend(
            self._compare_items(
                expected_args.get("items", []),
                actual_args.get("items", []),
            )
        )
        return results

    def _validate_model_facing_shape(
        self, actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        customer = actual_args.get("customer", {})
        if isinstance(customer, dict) and customer.get("email") is not None:
            results.append(
                MatchDetail(
                    "customer.email",
                    False,
                    "model-facing Olo args must not include customer.email",
                )
            )

        for field_path in self._find_forbidden_id_paths(actual_args):
            results.append(
                MatchDetail(
                    field_path,
                    False,
                    "model-facing Olo args must use handles, not raw Olo ids",
                )
            )

        return results

    def _find_forbidden_id_paths(
        self,
        value: Any,
        field_path: str = "",
    ) -> list[str]:
        if isinstance(value, dict):
            paths: list[str] = []
            for key, child_value in value.items():
                child_path = f"{field_path}.{key}" if field_path else str(key)
                if str(key).lower() in self.FORBIDDEN_ID_KEYS:
                    paths.append(child_path)
                paths.extend(self._find_forbidden_id_paths(child_value, child_path))
            return paths

        if isinstance(value, list):
            paths = []
            for index, child_value in enumerate(value):
                paths.extend(
                    self._find_forbidden_id_paths(
                        child_value,
                        f"{field_path}[{index}]",
                    )
                )
            return paths

        return []

    @staticmethod
    def _normalize_phone(phone: str | None) -> str | None:
        if phone is None:
            return None
        return re.sub(r"\D", "", phone)

    def _compare_customer(
        self,
        expected_customer: dict[str, Any],
        actual_customer: dict[str, Any],
    ) -> list[MatchDetail]:
        results: list[MatchDetail] = []

        for field in ["first_name", "last_name"]:
            expected_value = expected_customer.get(field)
            if expected_value is not None:
                results.append(
                    self._compare_named_value(
                        field_path=f"customer.{field}",
                        expected=expected_value,
                        actual=actual_customer.get(field),
                    )
                )

        expected_phone = self._normalize_phone(expected_customer.get("phone"))
        actual_phone = self._normalize_phone(actual_customer.get("phone"))
        if expected_phone is not None:
            if expected_phone == actual_phone:
                results.append(MatchDetail("customer.phone", True, f"{actual_phone!r}"))
            else:
                results.append(
                    MatchDetail(
                        "customer.phone",
                        False,
                        f"expected {expected_phone!r}, got {actual_phone!r}",
                    )
                )

        return results

    def _compare_items(
        self,
        expected_items: list[dict[str, Any]],
        actual_items: list[dict[str, Any]],
    ) -> list[MatchDetail]:
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

        for index, (expected_item, actual_item) in enumerate(
            zip(expected_items, actual_items, strict=True)
        ):
            item_path = f"items[{index}]"
            results.append(
                self._compare_named_value(
                    field_path=f"{item_path}.item_handle",
                    expected=expected_item.get("item_handle"),
                    actual=actual_item.get("item_handle"),
                )
            )

            expected_quantity = expected_item.get("quantity")
            if expected_quantity is not None:
                actual_quantity = actual_item.get("quantity")
                if expected_quantity == actual_quantity:
                    results.append(
                        MatchDetail(
                            f"{item_path}.quantity",
                            True,
                            f"{actual_quantity}",
                        )
                    )
                else:
                    results.append(
                        MatchDetail(
                            f"{item_path}.quantity",
                            False,
                            f"expected {expected_quantity}, got {actual_quantity}",
                        )
                    )

            if expected_item.get("selection_handles") or actual_item.get(
                "selection_handles"
            ):
                results.extend(
                    self._compare_selection_handles(
                        expected_item.get("selection_handles", []),
                        actual_item.get("selection_handles", []),
                        item_path,
                    )
                )

            if expected_item.get("selections") or actual_item.get("selections"):
                results.extend(
                    self._compare_selections(
                        expected_item.get("selections", []),
                        actual_item.get("selections", []),
                        item_path,
                    )
                )

        return results

    def _compare_selection_handles(
        self,
        expected_handles: list[str],
        actual_handles: list[str],
        item_path: str,
    ) -> list[MatchDetail]:
        if Counter(expected_handles) == Counter(actual_handles):
            return [
                MatchDetail(
                    f"{item_path}.selection_handles",
                    True,
                    f"{actual_handles!r}",
                )
            ]
        return [
            MatchDetail(
                f"{item_path}.selection_handles",
                False,
                f"expected {expected_handles!r}, got {actual_handles!r}",
            )
        ]

    def _compare_selections(
        self,
        expected_selections: list[dict[str, Any]],
        actual_selections: list[dict[str, Any]],
        item_path: str,
    ) -> list[MatchDetail]:
        if len(expected_selections) != len(actual_selections):
            return [
                MatchDetail(
                    f"{item_path}.selections",
                    False,
                    f"count mismatch: expected {len(expected_selections)}, got {len(actual_selections)}",
                )
            ]

        expected_counter = Counter(
            self._selection_key(selection) for selection in expected_selections
        )
        actual_counter = Counter(
            self._selection_key(selection) for selection in actual_selections
        )
        if expected_counter == actual_counter:
            return [
                MatchDetail(
                    f"{item_path}.selections",
                    True,
                    f"{actual_selections!r}",
                )
            ]

        return [
            MatchDetail(
                f"{item_path}.selections",
                False,
                f"expected {expected_selections!r}, got {actual_selections!r}",
            )
        ]

    def _selection_key(self, selection: dict[str, Any]) -> tuple[Any, Any]:
        return (selection.get("selection_handle"), selection.get("quantity", 1))


class GenericSubsetArgumentEvaluator(ToolArgumentEvaluator):
    """Generic evaluator for simple tool arguments.

    Only fields present in expected args are compared. Extra actual fields are ignored.
    """

    def evaluate(
        self, expected_args: dict[str, Any], actual_args: dict[str, Any]
    ) -> list[MatchDetail]:
        return self._compare_value("", expected_args, actual_args)

    def _compare_value(
        self,
        field_path: str,
        expected: Any,
        actual: Any,
    ) -> list[MatchDetail]:
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return [
                    MatchDetail(
                        field_path or "args",
                        False,
                        f"expected object, got {type(actual).__name__}",
                    )
                ]
            results: list[MatchDetail] = []
            for key, expected_value in expected.items():
                child_path = f"{field_path}.{key}" if field_path else str(key)
                actual_value = actual[key] if key in actual else MISSING
                results.extend(
                    self._compare_value(child_path, expected_value, actual_value)
                )
            return results

        if isinstance(expected, list):
            if not isinstance(actual, list):
                return [
                    MatchDetail(
                        field_path or "args",
                        False,
                        f"expected list, got {type(actual).__name__}",
                    )
                ]
            if len(expected) != len(actual):
                return [
                    MatchDetail(
                        field_path or "args",
                        False,
                        f"count mismatch: expected {len(expected)}, got {len(actual)}",
                    )
                ]
            results = []
            for index, expected_item in enumerate(expected):
                results.extend(
                    self._compare_value(
                        f"{field_path}[{index}]",
                        expected_item,
                        actual[index],
                    )
                )
            return results

        if actual is MISSING:
            return [MatchDetail(field_path or "args", False, "missing field")]

        return [
            self._compare_named_value(
                field_path=field_path or "args",
                expected=expected,
                actual=actual,
            )
        ]


# ---------------------------------------------------------------------------
# Evaluator registry
# ---------------------------------------------------------------------------

_EVALUATOR_REGISTRY: dict[str, type[ToolArgumentEvaluator]] = {
    "toast.": ToastArgumentEvaluator,
    "checkout_order": ToastArgumentEvaluator,
    "toast_takeout_create_order_v1": ToastArgumentEvaluator,
    "get_toast_item_details_v3": LookupArgumentEvaluator,
    "lookup_olo_order_options_v1": OloLookupArgumentEvaluator,
    "olo_create_order_v1": OloOrderArgumentEvaluator,
    "call_transfer": GenericSubsetArgumentEvaluator,
    "send_support_email": GenericSubsetArgumentEvaluator,
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
            if exp_tc.get("optional", False):
                continue
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
