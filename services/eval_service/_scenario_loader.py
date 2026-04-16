from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from services.eval_service.schema import EvalScenario

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def validate_scenarios_from_yaml(yaml_path: str | Path) -> list[EvalScenario]:
    """Load and validate EvalScenario objects from a YAML file.

    Args:
        yaml_path: Path to a YAML file containing a list of scenario dicts.

    Returns:
        A list of validated EvalScenario instances.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If the YAML content is not a list or a scenario fails validation.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)

    if not isinstance(raw, list):
        raise ValueError(
            f"Expected a YAML list of scenarios in {path}, got {type(raw).__name__}"
        )

    scenarios: list[EvalScenario] = []
    for idx, item in enumerate(raw):
        try:
            scenarios.append(EvalScenario.model_validate(item))
        except ValidationError as exc:
            raise ValueError(
                f"Scenario at index {idx} in {path} failed validation: {exc}"
            ) from exc

    return scenarios


def load_scenarios(
    project_id: str | None = None,
    scenario_category: str | None = None,
) -> list[EvalScenario]:
    """Load all EvalScenario objects from the scenarios directory.

    Recursively discovers every ``*.yaml`` and ``*.yml`` file under
    ``SCENARIOS_DIR``.  If *project_id* is provided only files inside a
    sub-directory whose name matches the project_id are loaded; otherwise
    every YAML file in the tree is loaded.

    If *scenario_category* is provided (e.g. ``"generic"``, ``"ordering"``),
    only scenarios under that subdirectory are loaded.

    Args:
        project_id: Optional project identifier used to filter scenarios to a
            specific sub-directory.
        scenario_category: Optional category subdirectory name to restrict
            which scenarios are loaded.

    Returns:
        A deduplicated (by file) list of EvalScenario objects.
    """
    if not SCENARIOS_DIR.exists():
        return []

    if project_id is not None:
        search_root = SCENARIOS_DIR / project_id
    elif scenario_category is not None:
        search_root = SCENARIOS_DIR / scenario_category
    else:
        search_root = SCENARIOS_DIR

    if not search_root.exists():
        return []

    scenarios: list[EvalScenario] = []
    for yaml_file in sorted(search_root.rglob("*.yaml")) + sorted(
        search_root.rglob("*.yml")
    ):
        scenarios.extend(validate_scenarios_from_yaml(yaml_file))

    return scenarios
