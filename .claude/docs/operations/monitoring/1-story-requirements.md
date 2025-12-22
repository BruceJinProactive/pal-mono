# Continuous Monitoring System - Story & Requirements

## Product Vision

Continuous monitoring provides real-time oversight of store operations through automated analysis. Store managers gain proactive issue detection without manual intervention, improving operational efficiency and compliance.

---

## Problem Statement

**Current Challenges:**

- Managers cannot monitor stores 24/7
- Issues go unnoticed until customers complain or inspections fail
- Manual checks are time-consuming and inconsistent
- Reactive approach leads to costly fixes and reputation damage

**Solution:**
Automated monitoring system that continuously analyzes store conditions through various inputs (cameras, sensors, data feeds) and alerts managers when issues arise.

---

## User Stories

### Manager - Source Management

**As a** store manager
**I want to** register monitoring sources (cameras, sensors)
**So that** I can monitor different aspects of my store operations

**Acceptance Criteria:**

- Can register device sources with connection details
- Can choose account-level (shared) or project-level (store-specific) scope
- Can test source connectivity before activation
- Can view source status and last activity
- Can edit or deactivate sources

---

### Manager - Setup Monitoring

**As a** store manager
**I want to** create monitoring configurations using registered sources
**So that** I can define what to check and when to alert

**Acceptance Criteria:**

- Can select from registered sources
- Can define AI analysis rules (text descriptions)
- Can set numeric thresholds for sensor data
- Can configure check frequency and active hours
- Can choose alert severity and delivery channels
- Can activate/deactivate configs without deletion

**Examples:**

- "Check front counter cleanliness every 30 minutes during business hours"
- "Verify staff presence at register every 15 minutes"
- "Monitor refrigerator temperature stays between 35-40°F"

---

### Manager - Receive Alerts

**As a** store manager
**I want to** receive timely alerts when issues are detected
**So that** I can take immediate corrective action

**Acceptance Criteria:**

- Receive alerts via email and in-app notifications
- Alert includes severity level (info, warning, critical)
- Alert shows captured data (image, sensor reading)
- Alert includes AI analysis explanation
- Can acknowledge alert to stop reminders
- Can resolve alert with notes

---

### Manager - Review History

**As a** store manager
**I want to** view monitoring history and past alerts
**So that** I can track patterns and demonstrate compliance

**Acceptance Criteria:**

- View timeline of all monitoring runs
- See captured data for each check
- Filter by date range, source, status
- Export data for compliance reporting
- Add notes and annotations to runs

---

### System - Automated Execution

**As the** monitoring system
**I need to** execute checks on schedule and generate alerts
**So that** managers receive timely notifications

**Acceptance Criteria:**

- Execute checks at configured frequency
- Respect active time windows
- Capture data from sources reliably
- Evaluate against defined rules using AI
- Generate alerts only when rules violated
- Log all runs for audit trail

---

## Core Concepts

### Input Source

A registered data provider that can be monitored. Sources are reusable and input-agnostic.

**Types:**

- **Device**: Physical hardware (cameras, temperature sensors, IoT devices)
- **Weather Feed**: Weather data for location _(future)_
- **Data Feed**: External APIs (delivery status, health inspections) _(future)_
- **Observation**: Staff-submitted reports _(future)_

**Key Properties:**

- Registered at account or project level
- Reusable across multiple monitoring configs
- Decoupled from monitoring rules

**Example:** A camera named "Front Counter Cam" is registered once but used by three different monitoring configs:

1. Staff presence check (every 15 min)
2. Cleanliness check (every hour)
3. Queue length monitor (every 5 min during peak hours)

### Monitoring Configuration

Defines what to monitor, evaluation rules, alert conditions, and schedule.

**Components:**

- **Source reference**: Which input source to use
- **Rules**: What conditions to check (AI prompts or thresholds)
- **Schedule**: How often and when to run
- **Alerts**: When to notify and through which channels

### Monitoring Run

A single execution of a monitoring check.

**Contains:**

- Timestamp of execution
- Captured data (image, sensor reading)
- Evaluation result (PASS/FAIL)
- AI analysis details
- Generated alerts (if any)

### Alert

Notification generated when monitoring detects an issue.

**Properties:**

- Severity level (info, warning, critical)
- Delivery channel (email, in-app, SMS _(future)_)
- Acknowledgment status
- Resolution status with notes

---

## Functional Requirements

### FR-1: Source Management

- Register device sources with connection details
- Test source connectivity
- Configure source-level settings
- Set source scope (account or project level)
- View source status and health
- Edit and deactivate sources

### FR-2: Monitoring Configuration

- Create configs referencing registered sources
- Define AI analysis rules using natural language
- Set numeric thresholds for sensors
- Configure check frequency (5/15/30/60 minutes)
- Set active time windows
- Configure timezone
- Choose alert channels and severity
- Enable/disable configs

### FR-3: Automated Execution

- Execute checks on configured schedule
- Respect active time windows
- Capture current state from source
- Evaluate using AI or threshold comparison
- Generate alerts on rule violations
- Log all runs to history

### FR-4: Alert Management

- Deliver alerts through configured channels
- Display in dashboard
- Support acknowledgment
- Support resolution with notes
- Track alert history

### FR-5: History & Reporting

- View timeline of monitoring runs
- Display captured data for each run
- Filter by date, source, status, config
- Export data for compliance
- Add annotations to runs

---

## Non-Functional Requirements

### Performance

- Alert generation: <30 seconds after detection
- Dashboard load time: <2 seconds
- Support 100+ concurrent monitoring configs per account
- Handle 10,000+ monitoring runs per day

### Reliability

- System uptime: >99.5%
- Alert delivery success: >99%
- Data retention: 90 days (configurable)

### Accuracy

- Alert accuracy: >90%
- False positive rate: <10%

### Security

- Source credentials stored in AWS Secrets Manager
- Role-based access control (manager, admin)
- Audit trail of all configuration changes
- Encrypted data transmission

### Scalability

- Horizontal scaling of monitoring workers
- Queue-based execution (AWS SQS)
- Efficient data storage and retrieval

---

## User Workflow Examples

### Example 1: Kitchen Temperature Monitoring

**Setup:**

1. Manager registers temperature sensor as device source
2. Creates monitoring config:
   - Rule: "Temperature must be between 35-40°F"
   - Schedule: Every 5 minutes, 24/7
   - Alert: Email on critical violations
3. Activates monitoring

**Execution:**

1. System checks temperature every 5 minutes
2. Reading: 45°F detected
3. Rule violated: Alert generated
4. Manager receives email with timestamp and reading
5. Manager acknowledges and adjusts refrigerator
6. Manager resolves alert with note: "Compressor issue fixed"

### Example 2: Front Counter Cleanliness

**Setup:**

1. Manager registers front counter camera
2. Creates monitoring config:
   - Rule: "Counter area should be clean and organized"
   - Schedule: Every 30 minutes, 6am-10pm
   - Alert: In-app notification on warnings
3. Activates monitoring

**Execution:**

1. System captures image at 2:30pm
2. AI analyzes: "Counter has food debris and disorganized items"
3. Rule violated: Warning alert generated
4. Manager sees in-app notification
5. Manager asks staff to clean counter
6. Manager resolves alert with note: "Counter cleaned at 2:45pm"

### Example 3: Multi-Purpose Camera Usage

**Setup:**

1. Manager registers "Main Dining Cam"
2. Creates three monitoring configs:
   - **Config A**: Check table cleanliness (every 30 min)
   - **Config B**: Monitor customer wait times (every 15 min during peak)
   - **Config C**: Verify safety compliance (every hour)
3. All three configs reference the same camera source

**Execution:**

1. Each config runs independently on its schedule
2. Same camera image used for different analyses
3. Separate alerts generated based on each config's rules
4. Manager receives alerts specific to each monitoring purpose

---

## MVP Scope

### Phase 1 (MVP) - Core Monitoring

**Included:**

- Device source type (cameras, temperature sensors)
- Single source per monitoring config
- Email and in-app alert channels
- Basic scheduling (frequency, active time windows)
- AI-based image analysis
- Numeric threshold comparisons
- Manual acknowledgment and resolution

**Success Criteria:**

- 10+ stores actively using monitoring
- 50+ monitoring configs deployed
- > 85% alert accuracy
- <15% false positive rate
- Manager satisfaction: 4/5 stars

### Phase 2 - Enhanced Sources

**Additions:**

- Weather feed integration
- Data feed sources (APIs)
- Multi-source monitoring configs
- Source health monitoring

### Phase 3 - Advanced Features

**Additions:**

- Observation sources (staff reports)
- SMS and push notification channels
- Advanced scheduling (cron expressions)
- Alert escalation rules
- Automated responses (trigger routines)
- Predictive analytics

---

## Success Metrics

### Operational Metrics

| Metric              | Target  | Measurement                          |
| ------------------- | ------- | ------------------------------------ |
| Alert accuracy      | >90%    | Manager feedback on alert relevance  |
| False positive rate | <10%    | Alerts acknowledged as false         |
| Time to detection   | <30 min | Issue occurrence to alert generation |
| Alert delivery rate | >99%    | Successful deliveries vs attempts    |
| System uptime       | >99.5%  | Monthly uptime percentage            |

### Adoption Metrics

| Metric                    | Target   | Measurement                       |
| ------------------------- | -------- | --------------------------------- |
| Active monitoring configs | 50+      | Configs with enabled=true         |
| Stores using monitoring   | 10+      | Projects with active configs      |
| Daily monitoring runs     | 1000+    | Successful executions per day     |
| Alert acknowledgment time | <2 hours | Time from alert to acknowledgment |

### Business Impact

| Metric                | Target     | Measurement                 |
| --------------------- | ---------- | --------------------------- |
| Issue resolution time | -30%       | Before/after comparison     |
| Compliance violations | -50%       | Health inspection failures  |
| Manager time savings  | 5 hrs/week | Survey + usage data         |
| Customer complaints   | -20%       | Related to monitored issues |

---

## Constraints & Assumptions

### Technical Constraints

- Camera sources must support RTSP/HTTP streaming or API access
- Sensors must provide real-time readings via API
- AI analysis requires clear images (minimum 720p)
- Alert delivery depends on external services (email, SMS)

### Business Constraints

- MVP focuses on device sources only
- Initial deployment limited to 10 pilot stores
- AI analysis uses existing LLM infrastructure
- Manager setup required (no auto-configuration)

### Assumptions

- Managers have access to source connection details
- Stores have reliable internet connectivity
- Sources remain accessible at configured locations
- Managers can respond to alerts within business hours
- Monitoring doesn't replace human judgment

---

## Risks & Mitigations

### Risk 1: High False Positive Rate

**Impact:** Managers ignore alerts, system loses credibility
**Mitigation:**

- Extensive testing during pilot phase
- Tunable confidence thresholds
- Manager feedback loop for rule refinement
- Clear alert severity levels

### Risk 2: Source Connectivity Issues

**Impact:** Missed monitoring runs, gaps in coverage
**Mitigation:**

- Source health monitoring
- Retry logic with exponential backoff
- Alert on source unavailability
- Fallback to last known state

### Risk 3: Alert Fatigue

**Impact:** Managers disable monitoring or miss critical alerts
**Mitigation:**

- Configurable alert frequency limits
- Alert grouping and deduplication
- Severity-based delivery channels
- Smart scheduling during active hours only

### Risk 4: AI Analysis Inconsistency

**Impact:** Unpredictable results, user frustration
**Mitigation:**

- Prompt engineering best practices
- Consistent evaluation criteria
- Historical context for comparison
- Human review of edge cases

---

## Dependencies

### Internal Systems

- **Agent System**: AI analysis and rule evaluation
- **Event System**: Alert delivery via EventBridge
- **Notification Service**: Email, in-app, SMS delivery
- **Storage**: S3 for captured images
- **Database**: PostgreSQL for configs and history

### External Services

- **AWS Secrets Manager**: Source credentials
- **AWS SQS**: Scheduled execution queue
- **AWS S3**: Image and data storage
- **SendGrid/Twilio**: Email/SMS delivery _(future)_

### Hardware/Infrastructure

- Camera sources with network access
- IoT sensors with API endpoints
- Stable internet connectivity at stores
- Claude API for AI analysis

---

## Open Questions

1. **Multi-tenant source sharing**: Should account-level sources be visible to all projects automatically or require explicit sharing?

2. **Alert deduplication**: If the same issue persists across multiple checks, send new alerts or group into one?

3. **Historical data access**: How long should captured images/data be retained? Cost vs compliance needs?

4. **AI model selection**: Use different models for different analysis types (vision vs text)? Performance vs accuracy trade-offs?

5. **Manager overrides**: Should managers be able to manually trigger checks outside the schedule?
