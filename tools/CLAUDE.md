# TOOLS

AI agent tools that extend agent capabilities with external integrations.

## Important Notes

- All exposed tools must be decorated with `@observe(as_type="tool")` for observability
- External API calls isolated in `_apis/` with `@observe` decorator from Langfuse
- Pydantic models in `classes.py` for validation
- Private files use underscore prefix (`_implementation.py`, `_utils.py`)
- Clean exports: `__init__.py` exports only main tool class
- Tools must be decoupled from services. It should only rely on repositories for data persistency

## File Structure

```tree
tools/{tool_name}/
├── __init__.py              # Export main tool class ONLY
├── _implementation.py       # Tool class (use @observe(as_type="tool") decorator)
├── classes.py              # Pydantic models (request/response)
└── _apis/
    ├── __init__.py         # API function implementations (use @observe decorator)
    └── _utils.py           # API utilities (connection, auth, token mgmt)
```

## Critical Patterns

### Tool Class (`_implementation.py`)

- Inherits from `Toolkit` (from agno.tools)
- Initialize: `super().__init__(name="tool_name")`
- Store `tool_metadata: ToolMetadata` as instance variable
- Methods with params decorated with `@params_validate()` (required ONLY if has params)
- Validation: Define `REQUIRED_{METHOD_NAME}_FIELDS = [...]` for param validation, e.g. REQUIRED_MAKE_RESERVATION_FIELDS

### Registration (`registry.py`)

```python
from tools.your_tool import YourTool

self._tools: Dict[str, Type[Toolkit]] = {
    "your_tool": YourTool,
}
```

### Metadata Access

Tools receive `ToolMetadata` via constructor if `access_metadata=True` in agent config:

- `customer_phone`: User's phone number
- `session_id`: Conversation session ID
- `agent_id`: Agent ID
- Other fields available in `agent.tool._config.ToolMetadata`

Use metadata instead of asking for known information.

## Adding a New Tool

1. Create directory: `tools/your_tool/`
2. Create files following structure above
3. Implement tool class in `_implementation.py`
4. Register in `tools/registry.py`

