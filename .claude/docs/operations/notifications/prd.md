# Notifications System PRD

## Overview

### Purpose

Enable restaurant teams to receive timely alerts and updates from Palona's operations systems through their preferred communication channels.

### Problem Statement

- Restaurant managers need to know immediately when something goes wrong (camera offline, food safety issue, missed routine)
- Staff need reminders and feedback on their tasks
- Current systems lack unified notification delivery

### Goals

- Keep restaurant teams informed in real-time
- Reduce response time to critical issues
- Provide flexibility in how users receive notifications
- Support busy kitchen environments with hands-free options

---

## Users & Their Needs

### Staff Members

| Need | Description |
|------|-------------|
| Task reminders | Know when routines are due |
| Feedback | Get notified if their work is rejected |
| Shift alerts | Receive shift-related notifications |

**Constraint**: Often have hands full, can't check phone constantly

### Store Managers

| Need | Description |
|------|-------------|
| Critical alerts | Immediate notification for food safety issues, equipment failures |
| Review queue | Know when work is ready for their review |
| Daily summary | Overview of what happened at their store |

**Constraint**: May manage multiple locations

### Restaurant Owners

| Need | Description |
|------|-------------|
| Cross-store visibility | High-level view of operations across all stores |
| Critical escalations | Only the most important issues |

**Constraint**: Don't want to be overwhelmed with alerts

---

## Notification Types

### Critical Alerts
Immediate attention required.

- Food safety violation detected
- Equipment/camera failure
- Routine missed after grace period
- Monitoring rule violation (e.g., "no staff in view")

### Action Required
User action needed but not urgent.

- Routine overdue - not started
- Submission ready for manager review
- Item flagged as out of acceptable range

### Informational
Awareness only, no immediate action needed.

- Routine due reminder
- Daily operations summary
- System health updates

---

## Communication Channels

| Channel | Best For | Example Use |
|---------|----------|-------------|
| Email | Non-urgent updates, summaries | Daily digest, evidence ready for review |
| SMS | Time-sensitive alerts | Routine overdue, critical violations |
| Voice Call | Critical alerts in loud/busy environments | Food safety emergency, equipment failure |
| In-App | All notifications with full context | Complete notification history |

### Voice Call Exploration

For busy kitchen environments where staff can't check their phones, an automated voice call could announce critical alerts:

> "Attention: Temperature log overdue for walk-in cooler."

This hands-free approach ensures critical information reaches staff even when they're occupied with food prep or service.

---

## User Preferences

Users should be able to:

- **Channel selection**: Choose which channels they receive notifications on
- **Quiet hours**: Set do-not-disturb periods (e.g., no notifications 10pm-7am)
- **Digest option**: Opt into daily digest emails instead of individual alerts
- **Mute types**: Silence specific notification types

---

## Notification Triggers by System

### From Input Sources

| Trigger | Who Gets Notified |
|---------|-------------------|
| Camera goes offline | Store manager |
| Camera feed becomes stale | Store manager |
| Connection test fails | Store manager |

### From Monitoring

| Trigger | Who Gets Notified |
|---------|-------------------|
| Monitoring rule fails (e.g., cleanliness check) | Store manager |
| Threshold exceeded | Store manager |
| Critical condition detected | Manager + escalation |

### From Routines

| Trigger | Who Gets Notified |
|---------|-------------------|
| Routine due (reminder) | Assigned staff |
| Routine overdue | Store manager |
| Routine missed | Store manager |
| Evidence submitted for review | Store manager |
| Item flagged out of range | Store manager |
| Submission rejected | Assigned staff |

---

## Daily Digest

Managers can opt to receive a daily summary email containing:

- Routines completed vs missed
- Items flagged for attention
- Monitoring alerts triggered
- System health status

**Delivery**: Sent at a configurable time (default: 8:00 AM local time)

---

## Success Metrics

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Critical alert response time | <15 min | Faster response to food safety issues |
| Routine completion rate | >95% | Better compliance |
| Manager review time | <24 hours | Faster feedback loop |
| Notification delivery rate | >99% | Reliable system |

---

## MVP Scope

### Phase 1

- Email and SMS notifications
- Real-time delivery
- Basic preference settings
- Routines system integration

### Phase 2

- Voice call channel
- Daily digest emails
- Monitoring and Inputs integration
- Quiet hours

### Phase 3

- Push notifications (mobile app)
- Advanced preferences
- Multi-location aggregation

---

## Appendix A: Voice Channels for GMs & Owners

Additional channels to reach GMs and owners directly on their phones.

### Channels

| Channel | When to Use |
|---------|-------------|
| SMS | Default for all alerts to GMs/owners |
| Voice Call | Critical alerts; escalation when SMS not acknowledged |

### Escalation

1. SMS sent to GM
2. If no response → Voice call to GM
3. If still no response → SMS + Voice call to Owner
