# Monitoring System - Detailed Database Design

## Overview

**Purpose**: Continuous monitoring system for store operations through automated analysis

**Architecture**: Multi-tenant with account and project level isolation

**Data Retention**: 90 days for runs, 1 year for resolved alerts

---

## Table 1: monitoring_configs

**Purpose**: Define what to check, when to check, and how to alert

### Column Design

```
┌─ Identity ────────────────────────────────────────────────┐
│ id              → Unique check ID                         │
│ project_id      → Which store this belongs to             │
│ name            → "Counter Cleanliness Monitor"           │
│ description     → "Checks every 30 mins during hours"     │
└───────────────────────────────────────────────────────────┘

┌─ What to Monitor ─────────────────────────────────────────┐
│ input_source_id → Which camera/sensor to use              │
│ rules           → AI prompt with templates                │
│                   Reference images (single/multiple)      │
│                   Threshold rules                         │
│                   See "Rules Column Structure" below      │
└───────────────────────────────────────────────────────────┘

┌─ When to Run ─────────────────────────────────────────────┐
│ trigger_mode         → "manual" / "auto" / "scheduled"    │
│                        Phase 1: manual, auto              │
│                        Phase 2: scheduled                 │
│ frequency            → Every 5/15/30/60 minutes           │
│                        (only used when trigger_mode =     │
│                         "scheduled")                      │
│ active_hours_start   → Start time (e.g., 6:00 AM)         │
│ active_hours_end     → End time (e.g., 10:00 PM)          │
│ timezone             → "America/Los_Angeles"              │
│ enabled              → On/Off toggle                      │
└───────────────────────────────────────────────────────────┘



┌─ Execution Tracking ──────────────────────────────────────┐
│ last_run_at          → Last execution timestamp           │
│ next_scheduled_run_at→ Next execution timestamp           │
└───────────────────────────────────────────────────────────┘

┌─ Audit Trail ─────────────────────────────────────────────┐
│ created_at      → When set up                             │
│ updated_at      → Last modified                           │
│ created_by      → Who created it                          │
└───────────────────────────────────────────────────────────┘
```

### Business Rules

- ✅ Name must be unique per store
- ⛔ Cannot delete if open alerts exist
- ✅ Cooldown prevents alert spam (default 60 min)
- ✅ Active hours respect store timezone

---

## Table 2: monitoring_runs

**Purpose**: Complete history of every check execution

### Column Design

```
┌─ Identity ────────────────────────────────────────────────┐
│ id                   → Unique run ID                      │
│ monitoring_config_id → Which check was executed           │
└───────────────────────────────────────────────────────────┘

┌─ Execution Timeline ──────────────────────────────────────┐
│ trigger_source       → "manual_api" / "auto" /            │
│                        "scheduled"                        │
│ trigger_metadata     → JSONB with trigger details         │
│                        S3: {bucket, key, event_time}      │
│                        API: {user_id, endpoint}           │
│                        Scheduled: {cron_job_id}           │
│ scheduled_at         → When supposed to run               │
│ started_at           → When actually started              │
│ completed_at         → When finished                      │
│ execution_duration_ms→ How long it took                   │
└───────────────────────────────────────────────────────────┘

┌─ Outcome ─────────────────────────────────────────────────┐
│ status      → Pending / Running / Completed / Failed      │
│ result      → Pass / Fail / Error                         │
│             → (null if not completed yet)                 │
└───────────────────────────────────────────────────────────┘

┌─ Captured Evidence ───────────────────────────────────────┐
│ captured_data   → Image URL, temperature reading, etc.    │
│                   Example: {"s3_key": "...", "temp": 45}  │
└───────────────────────────────────────────────────────────┘

┌─ Analysis Details ────────────────────────────────────────┐
│ evaluation_result → AI: "Counter has food debris"         │
│                     Threshold: "45°F exceeds max 40°F"    │
└───────────────────────────────────────────────────────────┘

┌─ Error Information ───────────────────────────────────────┐
│ error_message  → "Camera connection timeout"              │
│ error_details  → Technical error data                     │
└───────────────────────────────────────────────────────────┘

┌─ Metadata ────────────────────────────────────────────────┐
│ created_at     → Record created timestamp                 │
└───────────────────────────────────────────────────────────┘
```

### Business Rules

- 📝 Immutable: Never updated after completion
- 🗑️ Auto-deleted after 90 days
- ✅ Status = execution state, Result = pass/fail
- 📸 Images stored in S3, not database

### Business Rules

- ✅ Acknowledging ≠ Resolving (seen vs fixed)
- ✅ Resolution notes required when marking resolved
- 🗑️ Kept 1 year after resolution for compliance
- ⛔ Open/acknowledged alerts block config deletion
- 🔕 Cooldown prevents alert spam (from config)

---

## Entity Relationship Diagram

```
                          ┌──────────────────┐
                          │    projects      │
                          │                  │
                          │  • id (PK)       │
                          │  • account_id    │
                          └────────┬─────────┘
                                   │
                                   │ 1:N
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
          ┌──────────────┐ ┌──────────────────┐ │
          │input_sources │ │ monitoring_      │ │
          │(cameras,     │ │   configs        │ │
          │ sensors)     │ │                  │ │
          │              │ │  • id (PK)       │ │
          │ • id (PK)    │ │  • project_id    │ │
          │ • name       │ │  • input_source  │◄┘
          │ • type       ├─┤  • name          │
          │ • status     │ │  • rules         │  N:1 RESTRICT
          └──────────────┘ │  • frequency     │  (protect sources)
                           │  • alert_*       │
                           │  • enabled       │
                           └────────┬─────────┘
                                    │
                                    │ 1:N
                                    │ (cleanup history)
                                    ▼
                           ┌──────────────────┐
                           │ monitoring_runs  │
                           │                  │
                           │  • id (PK)       │
                           │  • config_id     │
                           │  • scheduled_at  │
                           │  • status        │
                           │  • result        │
                           │  • captured_data │
                           │  • evaluation_*  │
                           └────────┬─────────┘
                                    │
                                    │ 1:N
                                    │
                                    ▼
                           ┌──────────────────┐
                           │     alerts       │
                           │                  │
                           └──────────────────┘

```

### Key Design Patterns

🔒 **Multi-Tenant Isolation**

```
All queries filter by project_id
├─ monitoring_configs: direct project_id
├─ monitoring_runs: via configs.project_id
└─ alerts: direct project_id (denormalized!)
```

♻️ **Cascading Deletes**

```
Delete project
    └─► deletes configs
         └─► deletes runs
              └─► deletes alerts

Delete source
    └─► ⛔ BLOCKED if configs use it
```

⚡ **Denormalization**

```
alerts table includes:
├─ project_id ──► Skip JOIN for tenant filtering
└─ config_id ───► Skip JOIN for config filtering

Result: Dashboard queries 10x faster 🚀
```

📋 **Rules Column Structure (JSONB)**

**Single Reference Image:**

```
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "type": "ai_analysis",                               │
│   "prompt": "Compare to reference standard",           │
│   "reference_image_url": "s3://bucket/standard.jpg",  │
│   "confidence_threshold": 0.8                          │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Why: One standard picture for comparison
```

**Multiple Reference Images (Simple Array):**

```
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "type": "ai_analysis",                               │
│   "prompt": "Match any of these reference standards",  │
│   "reference_image_urls": [                            │
│     "s3://bucket/angle1.jpg",                         │
│     "s3://bucket/angle2.jpg",                         │
│     "s3://bucket/angle3.jpg"                          │
│   ],                                                   │
│   "comparison_mode": "best_match",                     │
│   "confidence_threshold": 0.8                          │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Why: Multiple reference angles or variations
```

**Multiple Reference Images (Time-Based):**

```
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "type": "ai_analysis",                               │
│   "reference_images": [                                │
│     {                                                  │
│       "label": "Morning Standard",                     │
│       "url": "s3://bucket/morning.jpg",               │
│       "weight": 0.6,                                   │
│       "time_applicable": "06:00-12:00"                │
│     },                                                 │
│     {                                                  │
│       "label": "Evening Standard",                     │
│       "url": "s3://bucket/evening.jpg",               │
│       "weight": 0.4,                                   │
│       "time_applicable": "12:00-22:00"                │
│     }                                                  │
│   ],                                                   │
│   "comparison_mode": "time_based",                     │
│   "confidence_threshold": 0.8                          │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Why: Different standards for different times
```

**Multiple Reference Images (Multi-Criteria):**

```
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "type": "ai_analysis",                               │
│   "reference_images": [                                │
│     {                                                  │
│       "label": "Counter Cleanliness",                  │
│       "url": "s3://bucket/clean-counter.jpg",         │
│       "weight": 0.5,                                   │
│       "criteria": "cleanliness"                        │
│     },                                                 │
│     {                                                  │
│       "label": "Item Placement",                       │
│       "url": "s3://bucket/placement.jpg",             │
│       "weight": 0.3,                                   │
│       "criteria": "organization"                       │
│     },                                                 │
│     {                                                  │
│       "label": "Staff Uniform",                        │
│       "url": "s3://bucket/uniform.jpg",               │
│       "weight": 0.2,                                   │
│       "criteria": "appearance"                         │
│     }                                                  │
│   ],                                                   │
│   "comparison_mode": "weighted_average",               │
│   "confidence_threshold": 0.75                         │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Why: Check multiple aspects at once
```

**Comparison Modes:**

```
├─ best_match       → Match ANY reference (OR logic)
│                     Use: "Pass if similar to ANY standard"
│                     Example: Multiple camera angles
│
├─ all_must_pass    → Match ALL references (AND logic)
│                     Use: "Must meet ALL standards"
│                     Example: Every criteria must pass
│
├─ weighted_average → Scored combination
│                     Use: "Blend multiple standards with weights"
│                     Example: Multi-criteria with importance
│
└─ time_based       → Auto-select by time
                      Use: "Different standards by hour"
                      Example: Morning vs evening standards
```

### 🎯 **Prompt Template System**

**How It Works:**

```
┌─────────────────────────────────────────────────────────┐
│ At Runtime:                                             │
│                                                         │
│ 1. Load config from database (monitoring_configs.rules)│
│ 2. Extract prompt template with {{variables}}         │
│ 3. Extract prompt_variables from same JSONB           │
│ 4. Replace {{variables}} with actual values           │
│ 5. Build final prompt                                  │
│ 6. Send to AI for analysis                             │
└─────────────────────────────────────────────────────────┘
```

**Where Variables Come From:**

```
Three Sources:

1. Static (Stored in Config)
   └─ Defined in prompt_variables object
   └─ Example: {"business": "bakery", "zones": [...]}

2. System Auto-Injected (Runtime)
   └─ System provides automatically
   └─ Example: {{current_time}}, {{current_hour}}

3. From Input Source (Database Join)
   └─ Pulled from input_sources table
   └─ Example: {{input_source.name}}, {{input_source.location}}
```

**Basic Template Example:**

```
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "type": "ai_analysis",                               │
│   "prompt": {                                          │
│     "role": "{{role}}",                                │
│     "context": "{{context}}",                          │
│     "instructions": [                                  │
│       {                                                │
│         "step": "{{step_1}}",                          │
│         "content": "{{step_1_content}}"                │
│       },                                               │
│       {                                                │
│         "step": "{{step_2}}",                          │
│         "content": "{{step_2_content}}"                │
│       }                                                │
│     ],                                                 │
│     "rules": "{{rules}}",                              │
│     "output_format": "{{output_format}}"               │
│   },                                                   │
│   "prompt_variables": {                                │
│     "role": "AI Inventory Monitor",                   │
│     "context": "Bakery with {{zone_count}} zones",    │
│     "zone_count": "2"                                  │
│   },                                                   │
│   "reference_image_urls": [                            │
│     "s3://bucket/zone-boundary-map.png"               │
│   ]                                                    │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Why: Multi-part structured prompts with templates
```

**Variable Resolution:**

```
┌─────────────────────────────────────────────────────────┐
│ Static Variables (from config):                        │
│                                                         │
│ Template: "Monitor {{business}} {{zones}}"             │
│ Variables: {                                           │
│   "business": "bakery",                                │
│   "zones": ["zone_1", "zone_2"]                        │
│ }                                                       │
│ Result: "Monitor bakery ['zone_1', 'zone_2']"         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ System Auto-Injected (runtime):                        │
│                                                         │
│ Template: "Time: {{current_time}}, Hour: {{current_hour}}"│
│ System Provides: {                                     │
│   "current_time": "2025-01-15T10:30:00",              │
│   "current_hour": "10",                                │
│   "day_of_week": "Monday"                              │
│ }                                                       │
│ Result: "Time: 2025-01-15T10:30:00, Hour: 10"        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ From Input Source (database):                          │
│                                                         │
│ Template: "Camera: {{input_source.name}}"             │
│ Database Query: SELECT name FROM input_sources         │
│ System Injects: {                                      │
│   "input_source.name": "Front Counter Camera"         │
│ }                                                       │
│ Result: "Camera: Front Counter Camera"                │
└─────────────────────────────────────────────────────────┘
```

**Example: Bakery Inventory Monitor (Full)**

```
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "type": "ai_analysis",                               │
│   "prompt": {                                          │
│     "role": "AI {{monitor_type}} Monitor for {{business}}",│
│     "image_definitions": {                             │
│       "reference": "Image A - {{reference_desc}}",     │
│       "target": "Image B - {{target_desc}}"            │
│     },                                                 │
│     "steps": [                                         │
│       {                                                │
│         "name": "STEP 1: IMAGE VALIDITY CHECK",        │
│         "checks": [                                    │
│           "Black/Dark/Corrupted",                      │
│           "Irrelevant Content"                         │
│         ],                                             │
│         "fail_action": "Set status to error"           │
│       },                                               │
│       {                                                │
│         "name": "STEP 2: ZONE DEFINITIONS",            │
│         "zones": "{{zones}}"                           │
│       },                                               │
│       {                                                │
│         "name": "STEP 3: ANALYSIS LOGIC",              │
│         "focus": "{{focus_item}}",                     │
│         "restock_rule": "{{restock_criteria}}"         │
│       }                                                │
│     ],                                                 │
│     "output_format": {                                 │
│       "type": "json",                                  │
│       "schema": "{{output_schema}}"                    │
│     }                                                  │
│   },                                                   │
│   "prompt_variables": {                                │
│     "monitor_type": "Inventory",                       │
│     "business": "bakery",                              │
│     "reference_desc": "Zone boundary map",             │
│     "target_desc": "Live CCTV image",                  │
│     "zones": [                                         │
│       {"id": "bread_zone_1", "location": "upper left"},│
│       {"id": "bread_zone_2", "location": "lower left"} │
│     ],                                                 │
│     "focus_item": "White plastic serving trays",       │
│     "restock_criteria": "ANY empty white tray",        │
│     "output_schema": "{details, overall_result, ...}"  │
│   },                                                   │
│   "reference_image_urls": [                            │
│     "s3://bakery/zone-boundary-map.png"               │
│   ],                                                   │
│   "confidence_threshold": 0.85                         │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Why: Complex multi-step analysis with structured sections
```

---
