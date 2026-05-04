# Eval case-spec → scenario YAML converter + Sonny's BBQ scenarios

**Date**: 2026-05-01
**Ticket**: PAL-10278
**Status**: Implemented (transitional — see "Relationship to eval-scenarios DB migration" below)
**Related**: `docs/records/2026-04-23-eval-scenarios-table.md`, `docs/records/2026-04-08-eval-ai-driven-turns.md`, `docs/records/2026-03-28-eval-platform-schema.md`

## Context

`pal-agents` produces "case-spec" JSON files describing Toast ordering test cases — customer opening utterance, item list with quantities, and selection trees (group/option/qualifier per modifier step). These drive its internal local-loop evaluation.

pal-mono's eval runner consumes a different shape: `EvalScenario` objects (see `services/eval_service/schema.py`), loaded from YAML via `_scenario_loader.validate_scenarios_from_yaml`, with AI-driven user turns and structured `expected_tool_calls`.

We needed to run pal-agents' Sonny's BBQ case-specs as first-class pal-mono eval scenarios without hand-translating thousands of entries.

## What shipped

### `services/eval_service/scripts/convert_case_specs.py` (new)

Pure/stateless JSON → YAML converter. Public surface (`__all__`):

- `convert_case_spec_file(src: Path, dst: Path) -> int` — file entrypoint
- `convert_case(case: dict) -> dict` — per-case converter (for in-memory use and testing)
- Helpers: `build_items_summary`, `build_lookup_targets`, `build_selection_paths`, `clean_item_for_speech`, `clean_option_for_speech`
- Constants: `HARD_RULES`, `DEFAULT_CUSTOMER`

Each case becomes one `EvalScenario` with:

- **`user_turns`**: the opening utterance + a single `ai_driven` turn whose `goal` names the ordered items in plain English, includes `HARD_RULES`, and a fixed `DEFAULT_CUSTOMER` persona (name/phone).
- **`expected_tool_calls`**: an optional `get_toast_item_details_v3` lookup (only when the case has at least one selection), followed by a required `toast_takeout_create_order_v1` call carrying the full `selection_paths` payload.

Speech-facing strings run through `clean_item_for_speech` / `clean_option_for_speech` to strip internal Toast codes like `(.32)`, `(1LB)`, `(MOD)`, `(3PD)`, `(FAM)`, etc. Raw Toast labels are preserved in the tool-call payloads so the expected-call matcher still lines up with real tool outputs.

YAML output uses a `yaml.SafeDumper` subclass with a string representer that emits `|` block-literal scalars for any multi-line string — keeps `persona` and AI-driven `goal` readable in diffs.

CLI:

```bash
uv run python -m services.eval_service.scripts.convert_case_specs \
    path/to/case_spec.json path/to/scenarios.yaml
```

Returns the number of scenarios written. Missing `cases` key is handled gracefully (empty list out).

### `tests/services/eval_service/scripts/test_convert_case_specs.py` (new)

19 tests covering:

- Speech cleaners strip internal Toast codes but preserve raw strings in tool payloads.
- `convert_case` produces a scenario that round-trips through `EvalScenario` validation.
- Lookup `get_toast_item_details_v3` call is emitted only when the case has selections.
- `convert_case_spec_file` writes YAML that re-parses via `validate_scenarios_from_yaml` into matching objects.
- Missing `cases` key → empty YAML list.

### `services/eval_service/scenarios/ordering/sonnys_bbq.yaml` (new, generated)

5,288 lines of scenarios generated from the pal-agents Sonny's BBQ case-spec corpus via the converter above. **Not hand-edited.** Regenerate from pal-agents source rather than patching this file directly.

## Relationship to the `eval_scenarios` DB migration

The in-flight `eval_scenarios` DB migration (`docs/records/2026-04-23-eval-scenarios-table.md`) will eventually replace filesystem YAML loading. Shipping a new filesystem YAML + a JSON→YAML converter now is an explicit transitional choice:

- The DB table's `raw_yaml` column stores the same YAML shape this converter produces, so the output is forward-compatible with the planned seed/backfill script — no schema rework needed at migration time.
- The converter's `convert_case` entrypoint is reusable at the row level: a future seed script can call it in-memory and insert rows directly, rather than going through a YAML file.
- When the YAML filesystem fallback is retired, `sonnys_bbq.yaml` will be backfilled into `eval_scenarios` by the seed script and the file deleted. Track under the eval-scenarios-db-migration line item in `docs/memory/short-term.md`.

## Files changed

| File | Change |
|------|--------|
| `services/eval_service/scripts/__init__.py` (new) | Package marker. |
| `services/eval_service/scripts/convert_case_specs.py` (new) | Converter module + CLI. |
| `tests/services/eval_service/scripts/__init__.py` (new) | Package marker. |
| `tests/services/eval_service/scripts/test_convert_case_specs.py` (new) | 19 tests. |
| `services/eval_service/scenarios/ordering/sonnys_bbq.yaml` (new, generated) | Sonny's BBQ ordering scenarios. |
| `services/eval_service/scenarios/project_map.json` | Mapped project `950d4f23-95fc-40ff-8505-ff40f10ae260` → `ordering/sonnys_bbq.yaml` so `_runner._resolve_scenario_files` picks it up. |

## Verification

- `uv run pytest tests/services/eval_service/scripts/ -q` → 19 passed.
- `./scripts/validate.sh --check` → clean (black, ruff, isort, pyright 0 errors, import-linter 2/2 kept, toml-sort).

## Consequences

### Benefits

- Sonny's BBQ ordering corpus is now runnable through pal-mono's eval platform without hand-translation.
- Eval `spec_modifier` / `apply_eval_safety` (2026-04-28) already guarantees these scenarios cannot submit real Toast orders, regardless of project config.
- Pure converter — no I/O beyond the explicit file entrypoint — makes the module trivially reusable by the future `eval_scenarios` seed script.

### Risks / limitations

- **Regeneration is one-shot from pal-agents.** If someone hand-edits `sonnys_bbq.yaml`, a re-run of the converter will clobber their edits. The header of this record and the module docstring both call this out; consider adding a generated-file banner at the top of the YAML if drift becomes a problem.
- **Selection-path fidelity is only as good as the case-spec.** The converter trusts the `steps[].group` / `steps[].option` values verbatim for tool payloads. Malformed input → malformed expected calls; the tests cover the conversion but not the upstream data quality.

## Follow-ups

1. When the `eval_scenarios` seed script lands, backfill `sonnys_bbq.yaml` and retire the file (see eval-scenarios DB migration plan).
2. If more restaurants adopt the pal-agents case-spec format, generalize any Sonny's-specific assumptions in the converter (currently only `DEFAULT_CUSTOMER` and the hard rules are customer-neutral — no Sonny's-specific logic lives in the converter itself).
