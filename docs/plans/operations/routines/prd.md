# Restaurant Routines System - Product Requirements Document

## Overview

A comprehensive routines system for restaurants to manage daily operations, food safety compliance, and staff accountability.

---

## MVP Scope

### Input Types
- **Photo only** for MVP
- System designed for future extension to: cameras, sensors, checkboxes, numeric inputs

### Hierarchy
- **Project-level routines** (store-specific) for MVP
- Corporate template system deferred to future phase

### Scheduling
- **EventBridge Scheduler** for automated routine generation

---

## Entity Relationship Chart

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STANDARD TIER                                     │
│  ┌──────────────┐         ┌──────────────────┐                              │
│  │   Routine    │ 1 ──► N │   RoutineItem    │                              │
│  │              │         │                  │                              │
│  │ - name       │         │ - name           │                              │
│  │ - project_id │         │ - input_type     │                              │
│  │ - is_active  │         │ - is_required    │                              │
│  │              │         │ - reference_img  │                              │
│  │              │         │ - ai_rules       │                              │
│  └──────┬───────┘         └──────────────────┘                              │
│         │                                                                   │
└─────────┼───────────────────────────────────────────────────────────────────┘
          │ 1
          │
          ▼ N
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WORKFLOW TIER                                     │
│  ┌──────────────────┐         ┌──────────────────┐                          │
│  │    Schedule      │ 1 ──► N │    Execution     │                          │
│  │                  │         │                  │                          │
│  │ - frequency      │         │ - scheduled_start│                          │
│  │ - start_time     │         │ - scheduled_end  │                          │
│  │ - end_time       │         │ - status         │                          │
│  │ - timezone       │         │ - assigned_user  │                          │
│  │ - days_of_week   │         │                  │                          │
│  └──────────────────┘         └────────┬─────────┘                          │
│                                        │                                    │
└────────────────────────────────────────┼────────────────────────────────────┘
                                         │ 1
                                         │
                                         ▼ 1
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EVIDENCE TIER                                     │
│  ┌──────────────────┐         ┌──────────────────┐                          │
│  │   Submission     │ 1 ──► N │  ItemResponse    │                          │
│  │                  │         │                  │                          │
│  │ - status         │         │ - status         │                          │
│  │ - submitted_by   │         │ - image_url      │                          │
│  │ - submitted_at   │         │ - ai_result      │                          │
│  │ - reviewed_by    │         │ - ai_passed      │                          │
│  │ - review_notes   │         │ - notes          │                          │
│  └────────┬─────────┘         └────────┬─────────┘                          │
│           │                            │                                    │
└───────────┼────────────────────────────┼────────────────────────────────────┘
            │                            │
            │         triggers           │ triggers
            ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ESCALATION TIER                                   │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                          Alert                                   │       │
│  │                                                                  │       │
│  │  - alert_type (overdue | missed | flagged_item | rejected)       │       │
│  │  - title, message, severity                                      │       │
│  │  - is_acknowledged, is_resolved                                  │       │
│  │  - references: execution_id, submission_id, item_response_id     │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Relationship Summary:
  Routine (1) ──► (N) RoutineItem     : A routine has many items
  Routine (1) ──► (N) Schedule        : A routine can have multiple schedules
  Schedule (1) ──► (N) Execution      : Each schedule generates many executions
  Execution (1) ──► (1) Submission    : Each execution has one submission
  Submission (1) ──► (N) ItemResponse : Each submission has responses per item
  Execution/Submission/ItemResponse ──► Alert : Various events trigger alerts
```

---

## Conceptual Hierarchy

The Routines system follows a 4-tier structure:

| Tier | Concept | Description |
|------|---------|-------------|
| **Standard** | Routine + Routine Items | Defines what needs to be done |
| **Workflow** | Schedule + Execution | When, how often, and who should complete |
| **Evidence** | Submission + Responses | Proof of completion collected by staff |
| **Escalation** | Alerts + Manager Review | Automated alerts and approval workflow |

---

## Use Cases

1. **Opening/Closing Routines** - Daily tasks before/after shifts
2. **Food Safety Routines** - Temperature logs, sanitation, expiration checks
3. **Compliance/Audit Routines** - Health department requirements, periodic inspections

## Frequency Requirements

- Multiple times daily (e.g., temperature checks every 4 hours)
- Once daily (opening/closing)
- Weekly/Monthly (deep cleaning, equipment maintenance)

---

## User Roles

| Role | Responsibilities |
|------|------------------|
| **Staff** | Complete routines via mobile app |
| **Manager** | Review evidence, approve/reject, view reports |
| **Corporate** | Create routine templates, view compliance across locations |

---

## Features

### 1. Routine Management (Standard Tier)

**Who**: Managers, Corporate admins

**Capabilities**:
- Create and edit routine templates
- Define routine items with various input types
- Categorize routines (opening, closing, food_safety, cleaning, compliance, custom)
- Copy routines between locations with customization

**Input Types Supported**:
| Type | Example |
|------|---------|
| Photo | "Take photo of clean prep station" |
| Number | "Enter walk-in cooler temperature" |
| Checkbox | "Did you sanitize cutting boards?" |
| Text | "Note any issues observed" |
| Multi-select | "Select cleaning tasks completed" |
| Camera verification | AI-powered visual verification |

### 2. Scheduling (Workflow Tier)

**Who**: Managers

**Capabilities**:
- Define when routines should be completed
- Set frequency: once, daily, weekly, monthly, or custom
- Configure specific times for daily routines
- Set grace periods (due within X minutes)
- Define active date ranges

### 3. Routine Execution (Workflow Tier)

**What the system does**:
- Automatically generates routine occurrences based on schedule
- Shows staff their pending routines ("You have 3 routines due")
- Tracks status: pending, in progress, completed, missed

### 4. Evidence Collection (Evidence Tier)

**Staff workflow**:
1. Start a routine → begins draft
2. Answer each item (photos, numbers, checkboxes, etc.)
3. Submit for review

**Evidence includes**:
- Responses for each item
- Photos and attachments
- Timestamps
- Location data (optional)
- Staff notes

### 5. Escalation (Escalation Tier)

**Automated alerts**:
- Routine overdue (not started by due time)
- Routine missed (not completed after grace period)
- Item flagged (value outside acceptable range)

**Manager review workflow**:
- Evidence awaiting review notification
- Approve or reject with notes
- If rejected, staff can resubmit

---

## User Flows

### Staff Completes Daily Opening Routine

1. Staff opens mobile app at 6:00 AM
2. Sees "Opening Routine" due at 6:30 AM
3. Taps to start
4. For each item:
   - Checkbox: Tap to check
   - Number: Enter value (flagged if out of range)
   - Photo: Take photo with phone camera
5. Taps "Submit"
6. Manager gets notification for review

### Manager Reviews Evidence

1. Manager opens web dashboard
2. Sees pending submissions
3. Opens submission, reviews each response
4. Can add notes, flag items for follow-up
5. Approves or rejects
6. If rejected: Staff notified to redo

### Missed Routine Alert

1. Due time passes without completion
2. System marks routine as missed
3. Manager receives alert notification
4. Gap logged for compliance audit trail

### Camera Auto-Verification

**Setup by manager**:
1. Register camera for the store
2. Upload reference image (e.g., clean floor photo)
3. Create routine item linked to camera
4. Set verification rules (e.g., "Floor must be clean")

**When staff completes routine**:
1. Staff sees "Kitchen Floor Check" item
2. Taps "Auto-verify with camera"
3. System compares camera image vs reference using AI
4. Result auto-fills: PASS or FAIL with explanation
5. Staff can override if needed, add notes

---

## Customization Model

- **Corporate template** defines standard routine
- **Per-location overrides** allowed (add items, adjust schedule)
- **Copy on customize** - stores get independent copies, changes don't flow back

---

## Primary Interface

- **Mobile app** for staff (completing routines on the floor)
- **Web dashboard** for managers (review, reporting)
- No offline support required

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Routine completion rate | >95% |
| Average completion time | <15 min for opening/closing |
| Manager review time | <24 hours |
| Missed routine rate | <5% |
| Out-of-range flag accuracy | >90% |
