# POS Toast Integration Endpoints

**Date**: 2026-05-19
**Status**: Implemented
**PR**: #4270 (PAL-10776)
**Related**: `docs/plans/pos-agent-onboarding.md`

## Context

Setting up a Toast ordering agent today requires an operator to manually
paste compiled menu JSON into the project integration form. The compilation
pipeline already exists in pal-mono (used by the Toast menu-update webhook),
but there is no API surface that calls it on demand.

## Goal

Expose one new read-only endpoint and extend one existing endpoint so the
manage-app can automate the integration setup without manual JSON pasting.

## API Changes

### New: `GET /accounts/{account_name}/integrations/{integration_id}/toast/options`

Read-only. Returns available menus and dining options for a given restaurant.
Credentials are read from the stored `Integration` row — no secrets in the URL.

| Param | Source |
|---|---|
| `account_name` | path |
| `integration_id` | path — already-stored account-level integration |
| `restaurant_guid` | query param — store identifier from Toast portal |

**Response** (`api/schemas/admin/pos_onboarding.py`):

```python
class DiningOption(BaseModel):
    guid: str
    name: str
    behavior: str   # e.g. "TAKE_OUT", "DELIVERY"

class ToastOptionsResponse(BaseModel):
    available_menus: list[str]           # top-level menu names from raw menu
    dining_options: list[DiningOption]
    suggested_takeout_guid: str | None   # set when exactly one TAKE_OUT option
    suggested_delivery_guid: str | None  # set when exactly one DELIVERY option
```

Requires `account.read` permission.

### Extended: `PUT /projects/{project_id}/integrations`

`CreateProjectIntegrationRequest` gains one new field and a `model_validator`:

```python
auto_fetch: bool = Field(default=False)
```

**When `auto_fetch=True` and `tool_name == "toast_v3"`:**

1. Reads `client_id` + `client_secret` from the `Integration` via secret manager
2. Calls `get_toast_access_token(client_id, client_secret)`
3. Calls `download_menu(bearer_token, config["restaurant_guid"])`
4. Calls `compile_toast_menu_v2(raw_menu, selected_menus=config.get("selected_menus"))` — `None` or `[]` compiles all menus
5. Populates `config["menu_data"]` from the compiled result

**When `auto_fetch=False` (default):** `config["menu_data"]` is used as-is.
Existing callers are unaffected.

### Validation (`model_validator` on `CreateProjectIntegrationRequest`)

For `tool_name == "toast_v3"`:

| Path | Rules |
|---|---|
| Both | `config.restaurant_guid` required and non-empty |
| `auto_fetch=True` | `config.menu_data` must be absent |
| `auto_fetch=False` | `config.menu_data` required (non-empty dict); `config.takeout_dining_option_guid` required |

## Files changed

| File | Change |
|---|---|
| `api/schemas/admin/pos_onboarding.py` (new) | `DiningOption`, `ToastOptionsResponse` |
| `api/schemas/admin/integration.py` | `auto_fetch` field + `model_validator` for toast_v3 config |
| `api/routes/admin/_toast_integration.py` (new) | `get_toast_options` handler |
| `api/routes/admin/_integration.py` | `_compile_toast_config` helper; auto-fetch path in `create_project_integration` |
| `api/routes/admin/__init__.py` | Register new GET endpoint |
| `tests/api/routes/admin/test_toast_integration.py` (new) | 28 unit tests |

## Verification

- `uv run pytest tests/api/routes/admin/test_toast_integration.py` → 28 passed
- `./scripts/validate.sh` → clean (black, ruff, isort, pyright, import-linter)

## Consequences

- Operators no longer paste compiled JSON for Toast integrations
- Existing integrations created with manual `menu_data` are unaffected (`auto_fetch` defaults to `False`)
- Menu re-compilation after menu changes: delete the existing project
  integration and re-create via `PUT /projects/{project_id}/integrations`
  with `auto_fetch=True` and updated `restaurant_guid` / `selected_menus`
  in config. The `PATCH` endpoint was not extended with `auto_fetch` in
  this PR.
