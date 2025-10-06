# Tool Standards & Guide

## Directory Layout (flexible, adapts to API design)
```text
tools/{tool_name}/
├── __init__.py              # Export main tool class only
├── _implementation.py       # Tool class with business logic
├── classes.py              # Pydantic models (requests/responses)
└── _apis/
    ├── __init__.py         # API function implementations
    └── _utils.py           # API utilities (connection, auth)
```

## Design Principles
- **Separation of Concerns:** Business logic in `_implementation.py`, API calls in `_apis/`, data models in `classes.py`
- **Clean Exports:** `__init__.py` exports only the main tool class (e.g., `from ._implementation import YourTool`)
- **Private Files:** Underscore prefix for implementation/utility files (`_implementation.py`, `_utils.py`)
- **Pydantic Models:** All API requests/responses defined as Pydantic models in `classes.py` with validation
- **API Layer:** All external API calls isolated in `_apis/` with `@task` decorator
- **Registration:** All tools must be registered in `tools/registry.py`

## Decorators
- `@tool` decorator required for ALL registered methods
- `@params_validate()` required ONLY for methods with parameters
- Missing `@tool` = method won't be instrumented

## Tool Class
- Inherit from `Toolkit`
- Initialize with `super().__init__(name="tool_name")`
- Store `tool_metadata` as instance variable
- Register all tool methods in `__init__`

## General Principles
- **Conciseness:** Methods ≤50 lines, focused, single-purpose
- **No Duplication:** Extract repeated logic into helpers
- **No Unused Code:** Remove unused imports, variables, methods, backup files
- **Type Hints:** All functions must specify parameter and return types

## Tool Docstrings
1. **Concise description** (1 line)
2. **When to use** (triggering conditions, user intents)
3. **Behavior** (success and failure outcomes)
4. **Args** (formats like "YYYY-MM-DD", constraints like min/max, examples)
5. **Returns** (success and error message formats)

**Key Rule:** All formats, constraints, and triggering conditions MUST be in docstring.

## Input Parameters
- **Required Only:** Only request parameters actually required by the API/operation
- **No Unnecessary Params:** Don't ask for information that can be derived or isn't needed
- **Avoid Extra LLM Calls:** Don't make additional LLM calls inside tool methods to extract/parse data
- **Direct Mapping:** Parameters should map directly to API requirements
- **Use Metadata:** Leverage `tool_metadata` (customer_phone, session_id, etc.) instead of asking

## Input Validation
- **Design:** Validate ALL inputs before external API calls or processing
- **Principle:** Fail fast with clear, specific error messages
- **Expectation:** Prevent API errors by catching invalid input early
- **User Experience:** Provide actionable feedback (formats, examples, constraints)

## Token Management
- **Caching:** Use global cached token with threading.Lock for thread-safe caching
- **Methods:** Implement `_get_token()` and `_reset_token()` methods
- **Auth Retry:** Detect auth errors (401, unauthorized) with `_is_auth_error()`
- **Retry Logic:** Retry once with fresh token on auth failure
- **Avoid Duplication:** Use helper methods to centralize retry logic

## Logging Convention
- **Format:** `[ToolName]: method_name - message`
- **debug:** Flow tracking, errors (with `traceback.format_exc()`)
- **info:** Important events (completions, transactions)
- **warning:** Fallbacks, deprecations
- **error:** Critical failures

## Attribution (if applied)
- Add "Via Palona AI" to notes/messages sent externally
- Add phone last 4 digits to names: `(*1234 via Palona)`

---