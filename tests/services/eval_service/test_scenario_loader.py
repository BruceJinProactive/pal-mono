"""Tests for services/eval_service/_scenario_loader.py.

Covers:
- Valid YAML parsing into EvalScenario objects
- Missing required fields raise ValueError
- AI-driven turns require a goal field
- load_scenarios returns empty list when directory is absent
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from services.eval_service._scenario_loader import (
    load_scenarios,
    validate_scenarios_from_yaml,
)
from services.eval_service.schema import EvalScenario, TurnType, UserTurn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, content: str, filename: str = "scenarios.yaml") -> Path:
    """Write *content* to a temporary YAML file and return its path."""
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Valid YAML parsing
# ---------------------------------------------------------------------------


class TestValidYamlParsing:
    def test_minimal_scenario(self, tmp_path: Path) -> None:
        """A scenario with only required fields should parse successfully."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-001
              scenario: "Customer asks for the menu"
              test_category: menu_inquiry
              user_turns:
                - "What's on the menu?"
            """,
        )

        scenarios = validate_scenarios_from_yaml(yaml_path)

        assert len(scenarios) == 1
        sc = scenarios[0]
        assert isinstance(sc, EvalScenario)
        assert sc.scenario_id == "sc-001"
        assert sc.test_category == "menu_inquiry"
        assert sc.persona == "standard_customer"  # default
        assert sc.user_turns == ["What's on the menu?"]
        assert sc.expected_tool_calls == []
        assert sc.context == []

    def test_full_scenario(self, tmp_path: Path) -> None:
        """A fully-specified scenario including tool calls and outcomes parses correctly."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-002
              scenario: "Place an order"
              test_category: ordering
              persona: vip_customer
              user_turns:
                - "I'd like to order a burger"
                - type: static
                  text: "Make it a double"
              expected_tool_calls:
                - tool: place_order
                  args:
                    item: burger
                    size: double
              expected_outcomes:
                task_completed: true
                hallucination: false
              context:
                - "Customer is a VIP member"
            """,
        )

        scenarios = validate_scenarios_from_yaml(yaml_path)

        assert len(scenarios) == 1
        sc = scenarios[0]
        assert sc.persona == "vip_customer"
        assert len(sc.user_turns) == 2
        assert sc.user_turns[0] == "I'd like to order a burger"
        turn1 = sc.user_turns[1]
        assert isinstance(turn1, UserTurn)
        assert turn1.text == "Make it a double"
        assert turn1.type == TurnType.STATIC
        assert len(sc.expected_tool_calls) == 1
        assert sc.expected_tool_calls[0].tool == "place_order"
        assert sc.expected_tool_calls[0].args == {"item": "burger", "size": "double"}
        assert sc.expected_outcomes.task_completed is True
        assert sc.expected_outcomes.hallucination is False
        assert sc.context == ["Customer is a VIP member"]

    def test_multiple_scenarios_in_one_file(self, tmp_path: Path) -> None:
        """Multiple scenario entries in a single file are all returned."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-010
              scenario: "First"
              test_category: cat_a
              user_turns:
                - "Hello"
            - scenario_id: sc-011
              scenario: "Second"
              test_category: cat_b
              user_turns:
                - "Goodbye"
            """,
        )

        scenarios = validate_scenarios_from_yaml(yaml_path)

        assert len(scenarios) == 2
        assert scenarios[0].scenario_id == "sc-010"
        assert scenarios[1].scenario_id == "sc-011"

    def test_ai_driven_turn_with_goal(self, tmp_path: Path) -> None:
        """An ai_driven turn that includes a goal field is accepted."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-020
              scenario: "Dynamic conversation"
              test_category: dynamic
              user_turns:
                - type: ai_driven
                  goal: "Find out the price of the combo meal"
            """,
        )

        scenarios = validate_scenarios_from_yaml(yaml_path)

        assert len(scenarios) == 1
        turn = scenarios[0].user_turns[0]
        assert isinstance(turn, UserTurn)
        assert turn.type == TurnType.AI_DRIVEN
        assert turn.goal == "Find out the price of the combo meal"


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    def test_missing_scenario_id_raises(self, tmp_path: Path) -> None:
        """A scenario without scenario_id should raise ValueError."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario: "Missing id"
              test_category: cat
              user_turns:
                - "Hi"
            """,
        )

        with pytest.raises(ValueError, match="failed validation"):
            validate_scenarios_from_yaml(yaml_path)

    def test_missing_scenario_raises(self, tmp_path: Path) -> None:
        """A scenario without the 'scenario' description field should raise ValueError."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-bad
              test_category: cat
              user_turns:
                - "Hi"
            """,
        )

        with pytest.raises(ValueError, match="failed validation"):
            validate_scenarios_from_yaml(yaml_path)

    def test_missing_test_category_raises(self, tmp_path: Path) -> None:
        """A scenario without test_category should raise ValueError."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-bad2
              scenario: "No category"
              user_turns:
                - "Hi"
            """,
        )

        with pytest.raises(ValueError, match="failed validation"):
            validate_scenarios_from_yaml(yaml_path)

    def test_missing_user_turns_raises(self, tmp_path: Path) -> None:
        """A scenario without user_turns should raise ValueError."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-bad3
              scenario: "No turns"
              test_category: cat
            """,
        )

        with pytest.raises(ValueError, match="failed validation"):
            validate_scenarios_from_yaml(yaml_path)

    def test_non_list_yaml_raises(self, tmp_path: Path) -> None:
        """A YAML file whose top-level value is not a list should raise ValueError."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            scenario_id: sc-dict
            scenario: "This is a dict, not a list"
            test_category: cat
            user_turns:
              - "Hi"
            """,
        )

        with pytest.raises(ValueError, match="Expected a YAML list"):
            validate_scenarios_from_yaml(yaml_path)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Pointing to a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            validate_scenarios_from_yaml(tmp_path / "does_not_exist.yaml")


# ---------------------------------------------------------------------------
# AI-driven turn validation
# ---------------------------------------------------------------------------


class TestAiDrivenTurnValidation:
    def test_ai_driven_turn_without_goal_is_accepted_by_schema(
        self, tmp_path: Path
    ) -> None:
        """Schema does not enforce goal presence — goal is Optional.

        If business logic later requires goal for ai_driven turns, a validator
        should be added to EvalScenario.  For now this test documents the
        current permissive behaviour.
        """
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-030
              scenario: "AI turn no goal"
              test_category: dynamic
              user_turns:
                - type: ai_driven
            """,
        )

        scenarios = validate_scenarios_from_yaml(yaml_path)
        turn = scenarios[0].user_turns[0]
        assert isinstance(turn, UserTurn)
        assert turn.type == TurnType.AI_DRIVEN
        assert turn.goal is None

    def test_static_turn_as_plain_string(self, tmp_path: Path) -> None:
        """Plain string turns are treated as static turns (str discriminator)."""
        yaml_path = _write_yaml(
            tmp_path,
            """
            - scenario_id: sc-031
              scenario: "String turns"
              test_category: basic
              user_turns:
                - "plain string turn"
            """,
        )

        scenarios = validate_scenarios_from_yaml(yaml_path)
        assert scenarios[0].user_turns[0] == "plain string turn"


# ---------------------------------------------------------------------------
# load_scenarios
# ---------------------------------------------------------------------------


class TestLoadScenarios:
    def test_returns_empty_list_when_scenarios_dir_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_scenarios returns [] when SCENARIOS_DIR does not exist."""
        import services.eval_service._scenario_loader as loader_module

        monkeypatch.setattr(loader_module, "SCENARIOS_DIR", tmp_path / "nonexistent")

        result = load_scenarios()
        assert result == []

    def test_loads_yaml_files_from_scenarios_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_scenarios discovers and loads all YAML files under SCENARIOS_DIR."""
        import services.eval_service._scenario_loader as loader_module

        scenarios_dir = tmp_path / "scenarios"
        (scenarios_dir / "generic").mkdir(parents=True)
        (scenarios_dir / "generic" / "basic.yaml").write_text(
            textwrap.dedent(
                """
                - scenario_id: sc-100
                  scenario: "Generic test"
                  test_category: generic
                  user_turns:
                    - "Hello"
                """
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(loader_module, "SCENARIOS_DIR", scenarios_dir)

        result = load_scenarios()
        assert len(result) == 1
        assert result[0].scenario_id == "sc-100"

    def test_load_scenarios_with_project_id_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_scenarios(project_id=...) only loads files from that sub-directory."""
        import services.eval_service._scenario_loader as loader_module

        scenarios_dir = tmp_path / "scenarios"
        (scenarios_dir / "proj-A").mkdir(parents=True)
        (scenarios_dir / "proj-B").mkdir(parents=True)

        (scenarios_dir / "proj-A" / "a.yaml").write_text(
            textwrap.dedent(
                """
                - scenario_id: sc-A
                  scenario: "Project A scenario"
                  test_category: cat_a
                  user_turns:
                    - "A turn"
                """
            ),
            encoding="utf-8",
        )
        (scenarios_dir / "proj-B" / "b.yaml").write_text(
            textwrap.dedent(
                """
                - scenario_id: sc-B
                  scenario: "Project B scenario"
                  test_category: cat_b
                  user_turns:
                    - "B turn"
                """
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(loader_module, "SCENARIOS_DIR", scenarios_dir)

        result = load_scenarios(project_id="proj-A")
        assert len(result) == 1
        assert result[0].scenario_id == "sc-A"

    def test_load_scenarios_unknown_project_id_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_scenarios with an unknown project_id returns an empty list."""
        import services.eval_service._scenario_loader as loader_module

        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        monkeypatch.setattr(loader_module, "SCENARIOS_DIR", scenarios_dir)

        result = load_scenarios(project_id="no-such-project")
        assert result == []

    def test_load_scenarios_with_category_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_scenarios(scenario_category=...) only loads from that subdirectory."""
        import services.eval_service._scenario_loader as loader_module

        scenarios_dir = tmp_path / "scenarios"
        (scenarios_dir / "generic").mkdir(parents=True)
        (scenarios_dir / "ordering").mkdir(parents=True)

        (scenarios_dir / "generic" / "greet.yaml").write_text(
            textwrap.dedent(
                """
                - scenario_id: sc-gen
                  scenario: "Generic"
                  test_category: generic
                  user_turns:
                    - "Hi"
                """
            ),
            encoding="utf-8",
        )
        (scenarios_dir / "ordering" / "order.yaml").write_text(
            textwrap.dedent(
                """
                - scenario_id: sc-ord
                  scenario: "Ordering"
                  test_category: ordering
                  user_turns:
                    - "Order pizza"
                """
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(loader_module, "SCENARIOS_DIR", scenarios_dir)

        generic_only = load_scenarios(scenario_category="generic")
        assert len(generic_only) == 1
        assert generic_only[0].scenario_id == "sc-gen"

        ordering_only = load_scenarios(scenario_category="ordering")
        assert len(ordering_only) == 1
        assert ordering_only[0].scenario_id == "sc-ord"

        all_scenarios = load_scenarios()
        assert len(all_scenarios) == 2

    def test_load_scenarios_unknown_category_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_scenarios with a non-existent category returns an empty list."""
        import services.eval_service._scenario_loader as loader_module

        scenarios_dir = tmp_path / "scenarios"
        scenarios_dir.mkdir()
        monkeypatch.setattr(loader_module, "SCENARIOS_DIR", scenarios_dir)

        result = load_scenarios(scenario_category="nonexistent")
        assert result == []
