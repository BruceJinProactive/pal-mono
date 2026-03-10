# Monitoring Config Restructure - Implementation Plan

**Date:** 2026-03-09
**Track:** Monitoring Configuration
**Estimated Effort:** 3-4 days
**Team Size:** 1 frontend + 1 backend

---

## Overview

Restructure the monitoring configuration to mirror the routines pattern. Replace the current free-text "Instructions" prompt and single-line "Monitoring Criteria" descriptions with structured fields: **context**, **pass criteria**, **fail criteria**, and **tagged reference images**.

**Key Deliverables:**

1. New monitoring config data model with `context`, `pass_criteria`, `fail_criteria`
2. Reference images with pass/fail flag and made optional
3. Updated Create and Edit forms matching the routines UI pattern
4. Backward-compatible migration for existing configs

**Scope Notes:**

- **In scope:** Backend model changes, API contract update, frontend types/forms/actions
- **Out of scope:** Monitoring run evaluation logic changes, dashboard/analytics changes
- **Dependencies:** Backend API must deploy before frontend can integrate

---

## Current State

### MonitoringRules (today)

```typescript
interface MonitoringRules {
  prompt: string; // free-text "Instructions" textarea
  reference_images: ReferenceImage[]; // required (>= 1 image), each has {id, url, description}
  structured_output?: StructuredOutputSchema;
  model?: ModelConfig;
  monitoring_time_window?: MonitoringTimeWindow;
}
```

### Current Create Request (FormData)

```text
signal_source_id:              "uuid-123"
name:                          "Kitchen Cleanliness Check"
description:                   "Monitors kitchen area"
prompt:                        "Check if the kitchen area is clean and properly maintained"
enabled:                       "true"
model:                         '{"provider":"google","model":"gemini-2.5-flash"}'
reference_images:              [File, File]
reference_image_descriptions:  ["Clean kitchen", "Dirty kitchen example"]
structured_output:             '[
  {
    "name": "result",
    "description": "Monitoring result value. 'pass': Criteria met (acceptable). 'fail': Criteria not met. 'error': Run failed",
    "required": true,
    "enum_values": ["pass", "fail", "error"],
    "enum_metadata": [...]
  },
  {
    "name": "details",
    "description": "Please explain in details why you give the result like this",
    "required": true
  }
]'
monitoring_time_window:        '{"enabled":true,"start_time":"06:00","end_time":"22:00"}'
```

### Current UI Fields

| Section             | Field                                               | Type     | Required   |
| ------------------- | --------------------------------------------------- | -------- | ---------- |
| Location            | Project selector                                    | dropdown | yes        |
| Camera              | Signal source selector                              | dropdown | yes        |
| Config Name         | text input                                          | string   | yes        |
| Description         | textarea                                            | string   | no         |
| Status              | toggle                                              | boolean  | yes        |
| AI Model            | model selector                                      | dropdown | yes        |
| Time Window         | toggle + start/end time                             | object   | no         |
| Instructions        | textarea                                            | string   | yes        |
| Monitoring Criteria | 3 single-line inputs (pass/fail/error descriptions) | strings  | yes        |
| Reference Images    | file upload + description per image                 | File[]   | yes (>= 1) |

---

## Target State

### MonitoringRules (proposed)

```typescript
interface MonitoringRules {
  context: string; // renamed from "prompt" — scene/context description
  pass_criteria: string[]; // NEW — list of conditions that indicate pass
  fail_criteria: string[]; // NEW — list of conditions that indicate fail
  reference_images: ReferenceImage[]; // CHANGED — now optional, each image tagged pass/fail
  structured_output?: StructuredOutputSchema;
  model?: ModelConfig;
  monitoring_time_window?: MonitoringTimeWindow;
}

interface ReferenceImage {
  id: string;
  url: string;
  description: string;
  flag: 'pass' | 'fail'; // NEW — marks image as pass or fail example
}
```

### Proposed Create Request (FormData)

```text
signal_source_id:              "uuid-123"
name:                          "Kitchen Cleanliness Check"
description:                   "Monitors kitchen area"
context:                       "Kitchen area during business hours. Camera faces the prep station."
pass_criteria:                 '["All surfaces are clean","Equipment properly stored","No visible debris"]'
fail_criteria:                 '["Visible food debris on surfaces","Equipment left out","Spills not cleaned"]'
enabled:                       "true"
model:                         '{"provider":"google","model":"gemini-2.5-flash"}'
reference_images:              [File, File, File]
reference_image_descriptions:  ["Clean prep area", "Dirty counter example", "Stocked shelf"]
reference_image_flags:         ["pass", "fail", "pass"]
structured_output:             '[
  {
    "name": "result",
    "description": "Monitoring result. 'pass': ALL pass criteria met: [All surfaces are clean, Equipment properly stored, No visible debris]. 'fail': ANY fail criteria observed: [Visible food debris on surfaces, Equipment left out, Spills not cleaned]. 'error': System could not evaluate.",
    "required": true,
    "enum_values": ["pass", "fail", "error"],
    "enum_metadata": [...]
  },
  {
    "name": "details",
    "description": "Please explain in details why you give the result like this",
    "required": true
  }
]'
monitoring_time_window:        '{"enabled":true,"start_time":"06:00","end_time":"22:00"}'
```

### Request Diff Summary

| Field                          | Before                                  | After                                                           |
| ------------------------------ | --------------------------------------- | --------------------------------------------------------------- |
| `prompt`                       | Free-text instructions (required)       | **Removed** — replaced by `context`                             |
| `context`                      | _(didn't exist)_                        | **New** — scene/context description (required)                  |
| `pass_criteria`                | _(didn't exist)_                        | **New** — JSON string array (required, >= 1)                    |
| `fail_criteria`                | _(didn't exist)_                        | **New** — JSON string array (required, >= 1)                    |
| `reference_images`             | Required (>= 1 image)                   | **Optional** (0 or more)                                        |
| `reference_image_descriptions` | `string[]` (one per image)              | Same — `string[]` (one per image)                               |
| `reference_image_flags`        | _(didn't exist)_                        | **New** — `("pass" \| "fail")[]` (one per image)                |
| `structured_output`            | Built from 3 manual description strings | Auto-built from criteria arrays; `error` is fixed system string |

### Proposed UI Fields

| Section          | Field                                                  | Type     | Required   | Change                                           |
| ---------------- | ------------------------------------------------------ | -------- | ---------- | ------------------------------------------------ |
| Location         | Project selector                                       | dropdown | yes        | _no change_                                      |
| Camera           | Signal source selector                                 | dropdown | yes        | _no change_                                      |
| Config Name      | text input                                             | string   | yes        | _no change_                                      |
| Description      | textarea                                               | string   | no         | _no change_                                      |
| Status           | toggle                                                 | boolean  | yes        | _no change_                                      |
| AI Model         | model selector                                         | dropdown | yes        | _no change_                                      |
| Time Window      | toggle + start/end time                                | object   | no         | _no change_                                      |
| Context          | textarea                                               | string   | yes        | **Renamed** from "Instructions"                  |
| Pass Criteria    | dynamic add/remove list                                | string[] | yes (>= 1) | **New** — replaces "Monitoring Criteria" section |
| Fail Criteria    | dynamic add/remove list                                | string[] | yes (>= 1) | **New** — replaces "Monitoring Criteria" section |
| Reference Images | file upload + description + pass/fail toggle per image | File[]   | **no**     | **Changed** — now optional, each image has flag  |

### Error State

The `error` state in the structured output is **system-determined** — not user-configurable. It means "the AI could not evaluate the image" (system failure). The UI does not show an error description input. The fixed string `"System could not evaluate"` is used automatically.

---

## Implementation Plan

### Phase 1: Backend Changes (Day 1-2)

#### Task 1.1: Update MonitoringRules Model

Add new fields to the backend `MonitoringRules` model:

```python
# MonitoringRules model — additions
context: str                              # renamed from prompt
pass_criteria: list[str]                  # required, min 1 item
fail_criteria: list[str]                  # required, min 1 item
```

Update `ReferenceImage` model:

```python
# ReferenceImage model — additions
flag: Literal["pass", "fail"]             # new field
```

#### Task 1.2: Update Create Endpoint

`POST /projects/{project_id}/monitoring/configs`

Accept new FormData fields:

- `context` (string) — replaces `prompt`
- `pass_criteria` (JSON string array)
- `fail_criteria` (JSON string array)
- `reference_image_flags` (repeated string, one per image: "pass" or "fail")

Validation:

- `context` required, max 2000 chars
- `pass_criteria` required, >= 1 item, each max 500 chars
- `fail_criteria` required, >= 1 item, each max 500 chars
- `reference_images` **optional** (0 or more)
- If images provided: count of images, descriptions, and flags must match

#### Task 1.3: Update PATCH Endpoint

`PATCH /projects/{project_id}/monitoring/configs/{config_id}`

Accept same new fields. All optional on PATCH.

#### Task 1.4: Update GET Response

Return new fields in `rules` object:

```json
{
  "rules": {
    "context": "Kitchen area during business hours...",
    "pass_criteria": ["All surfaces are clean", "Equipment properly stored"],
    "fail_criteria": ["Visible food debris", "Equipment left out"],
    "reference_images": [
      { "id": "uuid", "url": "https://...", "description": "Clean prep area", "flag": "pass" },
      { "id": "uuid", "url": "https://...", "description": "Dirty counter", "flag": "fail" }
    ],
    "structured_output": { ... },
    "model": { ... },
    "monitoring_time_window": { ... }
  }
}
```

#### Task 1.5: Migration

- Existing configs: `prompt` value migrates to `context`
- Existing configs: `pass_criteria` and `fail_criteria` default to `[]`
- Existing reference images: `flag` defaults to `"pass"`
- Backward compat: backend may accept `prompt` as alias for `context` during transition

---

### Phase 2: Frontend Types & Actions (Day 2)

#### Task 2.1: Update Types (`monitoring/types.ts`)

```typescript
// Updated ReferenceImage
export interface ReferenceImage {
  id: string;
  url: string;
  description: string;
  flag: 'pass' | 'fail'; // NEW
}

// Updated MonitoringRules
export interface MonitoringRules {
  context: string; // renamed from prompt
  pass_criteria: string[]; // NEW
  fail_criteria: string[]; // NEW
  reference_images: ReferenceImage[];
  structured_output?: StructuredOutputSchema;
  model?: ModelConfig;
  enum_metadata_map?: Record<string, EnumMetadata[]>;
  monitoring_time_window?: MonitoringTimeWindow;
}
```

Update `CreateMonitoringConfigSchema` (Zod):

```typescript
export const CreateMonitoringConfigSchema = z.object({
  signal_source_id: z.string().uuid(),
  name: z.string().min(1).max(255),
  description: z.string().max(2000).optional(),
  context: z.string().min(1).max(2000), // renamed from prompt
  pass_criteria: z.array(z.string().min(1).max(500)).min(1), // NEW
  fail_criteria: z.array(z.string().min(1).max(500)).min(1), // NEW
  enabled: z.boolean().default(true),
  reference_images: z.array(z.instanceof(File)).optional(), // NOW OPTIONAL
  reference_image_descriptions: z.array(z.string().max(500)).optional(),
  reference_image_flags: z.array(z.enum(['pass', 'fail'])).optional(), // NEW
});
```

#### Task 2.2: Update Actions (`monitoring/actions.ts`)

Update `createMonitoringConfig`:

- Send `context` instead of `prompt`
- Send `pass_criteria` as JSON string
- Send `fail_criteria` as JSON string
- Send `reference_image_flags` (one per image)
- Remove custom validation requiring >= 1 image

Update `updateMonitoringConfig`:

- Same field changes for PATCH

#### Task 2.3: Update State Description Utils

Update `formatStateDescriptions` to accept criteria arrays:

```typescript
export const formatStateDescriptions = (
  passCriteria: string[],
  failCriteria: string[],
): string => {
  const passStr = passCriteria.join(', ');
  const failStr = failCriteria.join(', ');
  return `Monitoring result. 'pass': ALL pass criteria met: [${passStr}]. 'fail': ANY fail criteria observed: [${failStr}]. 'error': System could not evaluate.`;
};
```

Update `parseStateDescriptions` for backward compat with old format.

---

### Phase 3: Frontend UI (Day 3-4)

#### Task 3.1: Update CreateConfigForm.tsx

**Remove:**

- `passDesc`, `failDesc`, `errorDesc` state variables
- "Monitoring Criteria" section (3 single-line inputs)
- Required validation for reference images (>= 1)

**Add:**

- `passCriteria: string[]` and `failCriteria: string[]` state
- **Context** textarea (replaces "Instructions" — same component, renamed label/placeholder)
- **Pass Criteria** section — dynamic add/remove list (match RoutineBuilder pattern):
  - Each criterion: `<Input>` + remove button
  - "Add Pass Criterion" button at bottom
  - Helper text: "What conditions indicate the image passes"
- **Fail Criteria** section — same pattern:
  - Each criterion: `<Input>` + remove button
  - "Add Fail Criterion" button at bottom
  - Helper text: "What conditions indicate the image fails"
- **Reference Images** — add pass/fail toggle per image:
  - Each image card: image preview + description input + pass/fail selector
  - Remove "at least one required" validation

**UI pattern reference:** `components/(console)/operation/routines/components/RoutineBuilder.tsx` lines 1061-1139

#### Task 3.2: Update EditConfigSidebar.tsx

Same changes as CreateConfigForm:

- Context textarea replacing Instructions
- Pass/Fail Criteria dynamic lists
- Reference image pass/fail flag
- Parse existing config into new fields

Backward compat:

- If config has `prompt` but no `context`: show `prompt` value in context field
- If config has old-style descriptions: show empty criteria lists (user must re-enter)
- If config has images without `flag`: default to `"pass"`

#### Task 3.3: Update Structured Output Generation

In both Create and Edit forms, auto-generate `structured_output` from criteria:

```typescript
const fields = [
  {
    name: 'result',
    description: formatStateDescriptions(passCriteria, failCriteria),
    required: true,
    enum_values: FIXED_RESULT_STATES.map((s) => s.name),
    enum_metadata: FIXED_RESULT_STATES,
  },
  {
    name: 'details',
    description: 'Please explain in details why you give the result like this',
    required: true,
  },
];
```

---

## Files Affected

| File                                                                                                | Change Type | Description                                                                                                             |
| --------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------- |
| `components/(console)/operation/monitoring/types.ts`                                                | Modify      | Add `context`, `pass_criteria`, `fail_criteria` to `MonitoringRules`; add `flag` to `ReferenceImage`; update Zod schema |
| `components/(console)/operation/monitoring/actions.ts`                                              | Modify      | Send new fields in FormData for create/update                                                                           |
| `components/(console)/operation/monitoring/components/monitoring-config/CreateConfigForm.tsx`       | Modify      | Replace Instructions + Criteria with Context + Pass/Fail lists; optional images with flag                               |
| `components/(console)/operation/monitoring/components/monitoring-config/EditConfigSidebar.tsx`      | Modify      | Same UI changes as create form + backward compat parsing                                                                |
| `components/(console)/operation/monitoring/components/monitoring-config/state-description-utils.ts` | Modify      | Accept criteria arrays instead of single strings                                                                        |
| `components/(console)/operation/monitoring/components/monitoring-config/structured-output-utils.ts` | Minor       | May need description generation updates                                                                                 |
| `components/(console)/operation/monitoring/components/monitoring-config/ConfigListCard.tsx`         | Minor       | Display context instead of prompt if shown                                                                              |
| `components/(console)/operation/monitoring/components/monitoring-records/`                          | Check       | Verify run results display still works                                                                                  |

---

## Backward Compatibility

| Scenario                                                | Handling                                                                                                    |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Existing config with `prompt`, no `context`             | Backend migrates `prompt` → `context`. Frontend falls back: `config.rules.context \|\| config.rules.prompt` |
| Existing config with no `pass_criteria`/`fail_criteria` | Default to `[]`. UI shows empty lists — user can add criteria on edit                                       |
| Existing reference images with no `flag`                | Default to `"pass"`                                                                                         |
| Old structured_output description format                | `parseStateDescriptions` handles both old and new formats                                                   |

---

## Testing Checklist

- [ ] Create config with context + criteria + no images → succeeds
- [ ] Create config with context + criteria + images (mix of pass/fail flags) → succeeds
- [ ] Edit existing old-format config → fields populate correctly, can save
- [ ] Edit new-format config → round-trips cleanly
- [ ] Pass criteria validation: at least 1 required
- [ ] Fail criteria validation: at least 1 required
- [ ] Reference images: 0 images allowed
- [ ] Reference images: flag persists through save/reload
- [ ] Structured output auto-generated correctly from criteria
- [ ] Mobile responsive (criteria lists, image cards with flag toggle)
- [ ] `pnpm tsc --noEmit` passes
- [ ] `pnpm lint` passes
