import uuid

from agent import ToolConfig, ToolIdentifier, ToolMetadata
from services.agent_service._implementation import _build_tool_specs

_DUMMY_UUID = uuid.uuid4()
_DUMMY_METADATA = ToolMetadata(
    agent_id=_DUMMY_UUID,
    account_id=_DUMMY_UUID,
    account_name="test",
    user_id=_DUMMY_UUID,
    session_id=_DUMMY_UUID,
    project_id=_DUMMY_UUID,
)


def _make_tool_config(tool_names: list[str]) -> ToolConfig:
    return ToolConfig(
        identifiers=[ToolIdentifier(tool_name=name, args={}) for name in tool_names],
        metadata=_DUMMY_METADATA,
    )


def test_build_tool_specs_includes_available_tools():
    config = _make_tool_config(["CalculatorTool", "WeatherTool"])
    specs = _build_tool_specs(config)
    assert len(specs) == 2
    assert {s.tool_name for s in specs} == {"CalculatorTool", "WeatherTool"}


def test_build_tool_specs_skips_unavailable_tools():
    config = _make_tool_config(["CalculatorTool", "ToastTool", "SquareTool"])
    specs = _build_tool_specs(config)
    assert len(specs) == 1
    assert specs[0].tool_name == "CalculatorTool"


def test_build_tool_specs_empty():
    config = _make_tool_config([])
    specs = _build_tool_specs(config)
    assert specs == []
