# Continuous Monitoring System - Product Requirements Document

## Overview

Continuous monitoring provides real-time oversight of store conditions via automated, scheduled analysis. It operates independently of the Routines system, enabling proactive issue detection without staff intervention.

---

## Core Concepts

### Input Sources

An **Input Source** represents any data provider that can be monitored. Sources are **input-agnostic** and **reusable**.

| Source Type | Description | Examples |
|-------------|-------------|----------|
| Device | Physical devices at the store | Cameras, temperature sensors, IoT devices |
| Weather Feed | Weather data for location | Temperature, severe weather alerts |
| Data Feed | External API integrations | Delivery service status, health dept feeds |
| Observation | Staff-submitted reports | Ad-hoc observations and notes |

**Key Properties:**
- A source can be registered at **account level** (shared across all stores) or **project level** (specific to one store)
- The **same source can be used by multiple monitoring configurations** for different purposes
- Sources are decoupled from monitoring rules - they just provide data

### Monitoring Configuration

A **Monitoring Configuration** defines what to monitor, how often, and when to alert. This is where rules and alerts live.

**Key Properties:**
- References one or more input sources
- Contains the **monitoring rules** (what to check)
- Contains the **alert configuration** (when and how to notify)
- Contains the **schedule** (how often to run)
- Multiple configs can reference the same source for different monitoring purposes

### Alerts

**Alerts** are generated when monitoring detects issues. Alerts are configured on the monitoring, not the source.

**Key Properties:**
- Created based on monitoring config rules
- Delivered through configured channels (email, push, SMS, etc.)
- Track acknowledgment and resolution

---

## Entity Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                         ACCOUNT                                  │
│  (can own sources shared across all projects)                   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ owns (account-level)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INPUT SOURCE                                │
│  - Reusable across multiple monitoring configs                  │
│  - Can be account-level OR project-level                        │
│  - Input-agnostic (device, weather, data feed, observation)     │
└─────────────────────────────────────────────────────────────────┘
         │
         │ referenced by (many-to-one)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MONITORING CONFIG                               │
│  - Defines rules to evaluate                                    │
│  - Defines alert conditions and channels                        │
│  - Defines schedule (frequency, active hours)                   │
│  - Multiple configs can use the SAME source                     │
└─────────────────────────────────────────────────────────────────┘
         │
         │ generates (one-to-many)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   MONITORING RUN                                 │
│  - Single execution of a monitoring check                       │
│  - Stores captured data and evaluation result                   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ triggers (one-to-many, conditional)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ALERT                                      │
│  - Generated when rules are violated                            │
│  - Delivered through configured channels                        │
│  - Tracks acknowledgment and resolution                         │
└─────────────────────────────────────────────────────────────────┘
```

### Example: Same Camera, Multiple Uses

```
Camera "Front Counter Cam" (Source)
         │
         ├──► Monitoring Config: "Staff Presence Check"
         │    - Rule: "Staff should be at counter"
         │    - Schedule: Every 15 min during business hours
         │    - Alert: Email manager on FAIL
         │
         ├──► Monitoring Config: "Counter Cleanliness"
         │    - Rule: "Counter area should be clean"
         │    - Schedule: Every hour
         │    - Alert: Push notification on FAIL
         │
         └──► Monitoring Config: "Queue Length Monitor"
              - Rule: "Alert if queue exceeds 5 people"
              - Schedule: Every 5 min during peak hours
              - Alert: SMS to shift lead on FAIL
```

---

## Features

### 1. Source Management

**Who**: Managers

**Capabilities**:
- Register devices (cameras, sensors) for the store or account
- Subscribe to weather feeds for location
- Connect external data feeds
- Configure source-specific settings (connection info, credentials)
- View source status and last activity

### 2. Monitoring Configuration

**Capabilities**:
- Create monitoring configs that reference any registered source
- Define AI analysis rules (e.g., "Floor must be clean", "Staff present")
- Set numeric thresholds (e.g., temperature min/max)
- Configure alert conditions (on fail, on pass, always)
- Set severity levels (info, warning, critical)
- Choose alert channels (email, push, SMS, in-app)

### 3. Scheduling

**Capabilities**:
- Set check frequency (e.g., every 5/15/30 minutes, hourly)
- Configure active time windows (only during business hours)
- Set timezone for schedule
- Enable/disable scheduling without deleting config

### 4. Alerts

**Alert triggers**:
- Rule violation detected
- Threshold exceeded
- Source unavailable/error

**Alert actions**:
- Deliver through configured channels
- Show in dashboard
- Track acknowledgment
- Track resolution with notes

### 5. Monitoring History

**Capabilities**:
- View history of all monitoring runs
- See captured data (images, readings) for each run
- Filter by date, status, config
- Review and annotate runs
- Export data for compliance

---

## User Flows

### Manager Registers a Camera Source

1. Manager navigates to Source Management
2. Selects "Add Source" → "Device"
3. Enters camera name, connection details
4. Chooses scope: account-level or project-level
5. Tests connection
6. Source is now available for monitoring configs

### Manager Creates Monitoring Config

1. Manager selects a registered source
2. Defines monitoring name and description
3. Sets rules: "Verify cleanliness", "Check for obstructions"
4. Configures schedule: Every 15 minutes, 6am-10pm
5. Configures alerts: Email on FAIL, warning severity
6. Activates monitoring

### System Runs Automated Check

1. Scheduled time arrives
2. System captures current state from source
3. AI evaluates against defined rules
4. Result determined: PASS or FAIL
5. If FAIL and alert configured: notification sent
6. Run logged to history

### Manager Reviews Alert

1. Manager receives alert notification
2. Opens dashboard to see alert details
3. Views captured data and AI analysis
4. Acknowledges alert
5. Takes corrective action
6. Resolves alert with notes

---

## MVP Scope

### Included in MVP
- Device source type (cameras, sensors)
- Single source per monitoring config
- Email and in-app alert channels
- Basic scheduling (frequency, active hours)
- AI-based image comparison rules

### Future Phases
- Weather Feed source type
- Data Feed source type (delivery APIs, etc.)
- Observation source type
- Multi-source monitoring with aggregation (all pass, any pass, majority)
- SMS and push notification channels
- Advanced scheduling (cron expressions)

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Alert accuracy | >90% |
| False positive rate | <10% |
| Time to detection | <30 minutes |
| Manager acknowledgment time | <2 hours |
| System uptime | >99.5% |
