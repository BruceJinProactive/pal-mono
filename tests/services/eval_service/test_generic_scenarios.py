"""Validates that every YAML file in services/eval_service/scenarios/generic/
parses correctly via validate_scenarios_from_yaml().

Each test is parameterized over the actual file on disk so failures report the
specific file name that broke.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.eval_service._scenario_loader import validate_scenarios_from_yaml
from services.eval_service.schema import EvalScenario

GENERIC_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "services"
    / "eval_service"
    / "scenarios"
    / "generic"
)

# Collect all YAML files at import time so pytest can parameterize them.
_YAML_FILES = sorted(GENERIC_DIR.glob("*.yaml")) + sorted(GENERIC_DIR.glob("*.yml"))

EXPECTED_CATEGORIES = {
    "greeting",
    "hours_inquiry",
    "address_inquiry",
    "allergy_safety",
    "escalation",
    "adversarial",
    "topic_switch",
    "off_topic",
    "language_switch",
    "repeat_request",
    "order_cancellation",
}

EXPECTED_FILE_STEMS = {
    "greeting",
    "hours_inquiry",
    "address_inquiry",
    "allergy_safety",
    "escalation",
    "adversarial",
    "topic_switch",
    "off_topic",
    "language_switch",
    "repeat_request",
    "order_cancellation",
}


class TestGenericScenarioFiles:
    def test_generic_dir_exists(self) -> None:
        """The generic scenarios directory must exist."""
        assert GENERIC_DIR.is_dir(), f"Expected directory at {GENERIC_DIR}"

    def test_all_expected_files_present(self) -> None:
        """Every required category YAML file must be present in the generic dir."""
        present_stems = {f.stem for f in _YAML_FILES}
        missing = EXPECTED_FILE_STEMS - present_stems
        assert not missing, f"Missing scenario files: {sorted(missing)}"

    def test_minimum_scenario_count(self) -> None:
        """At least 10 generic scenario files must exist."""
        assert (
            len(_YAML_FILES) >= 10
        ), f"Expected at least 10 generic scenario YAML files, found {len(_YAML_FILES)}"

    @pytest.mark.parametrize("yaml_file", _YAML_FILES, ids=lambda p: p.name)
    def test_yaml_file_parses_without_error(self, yaml_file: Path) -> None:
        """Each YAML file must parse into a non-empty list of EvalScenario objects."""
        scenarios = validate_scenarios_from_yaml(yaml_file)
        assert len(scenarios) >= 1, f"{yaml_file.name} contains no scenarios"
        for sc in scenarios:
            assert isinstance(sc, EvalScenario)

    @pytest.mark.parametrize("yaml_file", _YAML_FILES, ids=lambda p: p.name)
    def test_scenario_ids_are_unique_within_file(self, yaml_file: Path) -> None:
        """scenario_id values must be unique within each file."""
        scenarios = validate_scenarios_from_yaml(yaml_file)
        ids = [sc.scenario_id for sc in scenarios]
        assert len(ids) == len(
            set(ids)
        ), f"Duplicate scenario_id found in {yaml_file.name}: {ids}"

    @pytest.mark.parametrize("yaml_file", _YAML_FILES, ids=lambda p: p.name)
    def test_scenarios_have_non_empty_user_turns(self, yaml_file: Path) -> None:
        """Every scenario must have at least one user turn."""
        scenarios = validate_scenarios_from_yaml(yaml_file)
        for sc in scenarios:
            assert (
                len(sc.user_turns) >= 1
            ), f"Scenario {sc.scenario_id} in {yaml_file.name} has no user_turns"

    @pytest.mark.parametrize("yaml_file", _YAML_FILES, ids=lambda p: p.name)
    def test_scenarios_have_no_expected_tool_calls(self, yaml_file: Path) -> None:
        """Generic scenarios must not specify expected_tool_calls (restaurant-agnostic)."""
        scenarios = validate_scenarios_from_yaml(yaml_file)
        for sc in scenarios:
            assert sc.expected_tool_calls == [], (
                f"Scenario {sc.scenario_id} in {yaml_file.name} has expected_tool_calls; "
                "generic scenarios must be restaurant-agnostic"
            )

    def test_all_expected_categories_covered(self) -> None:
        """Every required test_category must appear in at least one scenario across all files."""
        all_categories: set[str] = set()
        for yaml_file in _YAML_FILES:
            for sc in validate_scenarios_from_yaml(yaml_file):
                all_categories.add(sc.test_category)
        missing = EXPECTED_CATEGORIES - all_categories
        assert not missing, f"Missing test categories: {sorted(missing)}"
