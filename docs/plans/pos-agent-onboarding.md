# POS Agent Onboarding

Last updated: 2026-05-19
Status: Proposed

---

## What we're building

A guided onboarding flow that takes a restaurant's POS credentials and produces
a fully configured ordering agent — with compiled menu, prompt setup, and an
initial eval run — without any manual JSON pasting or post-creation configuration.

Phase 1 covers Toast. Adora follows the same shape in Phase 2.

---

## System responsibilities

| System | Owns |
|---|---|
| **manage-app** | Collect all inputs; trigger each step; show progress |
| **pal-mono** | Auth, provider fetch, menu compile, all DB writes, eval run |
| **pal-agents** | Deterministic menu compilers and eval scenario generation (both called as libraries by pal-mono) |

---

## V1 approach: steps done separately

Steps 1, 2, and 3 (shell) require no new code for account, project, and agent creation. Step 3 reuses the existing form shell but requires new endpoints and a new checkbox UI (see below).

| Step | What | How |
|---|---|---|
| 1 | Create account | existing onboarding flow |
| 2 | Create project | existing onboarding flow |
| 3 | Set up POS integration | existing form shell (`ProjectIntegrations`); new endpoints + checkbox UI replace the JSON paste |
| 4 | Create agent | existing agent creation; `PromptsV2Manager` for capability defaults |
| 5 | Generate test cases | **Phase 2** — requires `pal_agents.generators.toast` |
| 6 | Start eval | **Phase 2** — depends on step 5 |

---

## Step 3: POS integration setup

The existing `ProjectIntegrations` form currently requires the operator to
paste compiled menu JSON. This plan extends the existing endpoints to
eliminate the manual paste — no new setup endpoint is needed.

**Current flow (unchanged):**
1. `PUT /accounts/{account_name}/integrations` — store credentials → `Integration` row
2. `PUT /projects/{project_id}/integrations` — caller supplies compiled `menu_data` in `config` → `ProjectIntegration` row

When `tool_name == "toast_v3"` and `restaurant_guid` is present, the handler
reads credentials from the already-stored `Integration`, fetches the raw menu,
compiles it, and populates `config.menu_data` automatically — any `menu_data`
in `config` is ignored. `takeout_dining_option_guid` and `selected_menus` are
optional and wired into the compiled config when provided. When
`restaurant_guid` is omitted, `menu_data` in `config` is used as-is
(backward-compatible manual path).

New fields added to `CreateProjectIntegrationRequest`:
- `restaurant_guid` — required when auto-compiling; also becomes `store_identifier`
- `selected_menus` — which menus to compile (from `GET /accounts/{account_name}/integrations/{integration_id}/toast/options`'s `available_menus`)
- `takeout_dining_option_guid` — required when auto-compiling; triggers auto-fetch together with `restaurant_guid`
- `delivery_dining_option_guid` — optional

**New options endpoint** — no DB writes. Called in the
UI once the operator has created the account-level integration (step 1 stores
credentials). The GET reads credentials from the stored integration so no
secrets appear in the URL:

```http
GET /accounts/{account_name}/integrations/{integration_id}/toast/options?restaurant_guid=...
  → { available_menus: string[], dining_options, suggested_takeout_guid? }
```

The form renders a checkbox list of `available_menus` (all checked by
default; operator unchecks test/operational menus — names like `Disposables`,
`Test Menu`, `Integration Requirements` are common in production), a dining
option picker if ambiguous, and optional feature flags.

Phase 1 supports Toast only; Adora is visible in the UI but disabled with a
"Phase 2" label.

## Step 5: Generate test cases

**Phase 2.** Triggered by a button on the project page once
`pal_agents.generators.toast` ships. Calls pal-mono which runs
`generate_l1_scenarios` against the compiled menu already stored in the
project integration. Scenarios are written to the `eval_scenarios` table
keyed by `project_id`.

---

## Step 6: Start eval

**Phase 2.** Triggered from the project page after step 5 completes.
Calls `eval_service.create_eval_run` with `triggered_by="manual"`.
`submit_orders` is forced `false` during eval (existing `apply_eval_safety`
spec modifier).

---

## What needs to be built

| What | Notes |
|---|---|
| `GET /accounts/{account_name}/integrations/{integration_id}/toast/options` | New endpoint; reads credentials from stored integration — no secrets in URL; no DB writes |
| Extend `PUT /projects/{project_id}/integrations` | Add `restaurant_guid`, `selected_menus`, `takeout_dining_option_guid`, `delivery_dining_option_guid` to `CreateProjectIntegrationRequest`; both `restaurant_guid` + `takeout_dining_option_guid` required to trigger auto-fetch; when omitted, `menu_data` in `config` is used as-is (backward-compatible manual path) |
| Menu checkbox UI in `ProjectIntegrations` | Replace free-text `SelectedMenusField` with fetched checkbox list |
| `eval_scenario_repository` | Table exists; repository class missing |
| Eval runner: load scenarios by project | Active work tracked in `docs/memory/short-term.md` |

Steps 1, 2, 4 require no new code. Step 6 reuses the existing eval run API.

---

## Phases

| Phase | Adds |
|---|---|
| 1 | Toast — steps done separately as described above |
| 2 | `pal_agents.generators.toast.generate_l1_scenarios` — new public module in `src/pal_agents/generators/`; wraps existing private `_build_menu_context` + `_generate_cases` from `evals/system_prompt_local_loop/toast/`; LLM-driven (gpt-4.1-mini); returns scenario dicts for `eval_scenarios.raw_yaml`; also requires `eval_scenario_repository` (table exists, class missing) and eval runner project-id loading (tracked in short-term.md) before steps 5 + 6 are functional |
| 3 | Adora support; guided wizard sequencing all steps in one flow |
| 4 | Multi-location batch; re-compile from project page after menu changes |
