# Voice AI Evaluation Platform — Timeline & Staffing
### March 2026

---

## Overview

| Phase | Calendar Weeks | Eng-Days | Max Parallel Engineers |
|-------|---------------|----------|----------------------|
| **Phase 1**: On-demand testing + fingerprinting | Weeks 1-2 | 15d | 2 |
| **Phase 2**: Audio-native evaluation | Weeks 2-4 (overlaps Phase 1) | 15d | 2 |
| **Phases 3-5**: Prod scoring + monitoring + CI | Weeks 4-5 | 10d | 2 |
| **Total** | **~5 weeks** | **~40d** | |

With 2 engineers throughout and aggressive cross-phase overlap, calendar time compresses from ~13 weeks to ~5. Engineer B starts Phase 2 work (P2-A1) while Engineer A finishes Phase 1. Phases 3-5 run with 2 engineers in parallel since most tasks only depend on P3-A1.

---

## Phase 1: On-Demand Testing + Fingerprinting

### Dependency Graph

```mermaid
graph TD
    A1["P1-A1<br/>SDK + AgentDriver<br/>pal-agents · 2.5d"] --> C2["P1-C2<br/>Eval service + evaluators<br/>pal-mono · 3d"]
    B2["P1-B2<br/>Scenario format + CRUD<br/>pal-mono · 1.5d"] --> C2
    C1["P1-C1<br/>DB tables<br/>pal-mono · 1.5d"] --> C2
    C1 --> E1["P1-E1<br/>Config snapshot<br/>pal-mono · 1d"]
    B1["P1-B1<br/>Fingerprinting<br/>pal-mono · 2d"] --> E1
    C2 --> C3["P1-C3<br/>API routes<br/>pal-mono · 1d"]
    C3 --> F1["P1-F1<br/>Batch script<br/>pal-mono · 0.5d"]

    style A1 fill:#e8f5e9,stroke:#2e7d32
    style B1 fill:#e8f5e9,stroke:#2e7d32
    style B2 fill:#e8f5e9,stroke:#2e7d32
    style C1 fill:#e8f5e9,stroke:#2e7d32
    style C2 fill:#fff3e0,stroke:#e65100
    style E1 fill:#e3f2fd,stroke:#1565c0
    style C3 fill:#e3f2fd,stroke:#1565c0
    style F1 fill:#e3f2fd,stroke:#1565c0
```

Green = no dependencies (start day 1). Orange = critical path. Blue = dependent work.

### Staffing: 2 Engineers, ~8 Calendar Days

```mermaid
gantt
    title Phase 1 - Two Engineers
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Engineer A (pal-agents + pal-mono)
    P1-A1 SDK + AgentDriver (pal-agents)       :a1, 2026-04-07, 3d
    P1-C2 Eval service + evaluators             :c2, after a1, 3d
    P1-C3 API routes                            :c3, after c2, 1d
    P1-F1 Batch script                          :f1, after c3, 1d

    section Engineer B (pal-mono)
    P1-B1 Fingerprinting                        :b1, 2026-04-07, 2d
    P1-C1 DB tables                             :c1, 2026-04-07, 2d
    P1-B2 Scenario format + CRUD                :b2, after c1, 2d
    P1-E1 Config snapshot                       :e1, after b1, 1d
```

| Day | Engineer A | Engineer B |
|-----|-----------|-----------|
| 1–2 | P1-A1 SDK + AgentDriver (pal-agents) | P1-B1 Fingerprinting + P1-C1 DB tables |
| 3 | P1-A1 finishes | P1-B2 Scenario format |
| 4–5 | P1-C2 Eval service + evaluators | P1-B2 finishes → P1-E1 Config snapshot |
| 6 | P1-C2 finishes | Available for review / FDE scenario authoring |
| 7 | P1-C3 API routes | Review + integration testing |
| 8 | P1-F1 Batch script | End-to-end validation |

**Critical path**: A1 → C2 → C3 → F1 (2.5 + 3 + 1 + 0.5 = 7 working days, ~8 calendar days with rounding). Engineer B's work feeds into C2 (needs DB tables + scenario format) but finishes before C2 starts on day 4.

**Phase 1 output**: FDE can run `POST /v1/eval/run { project_id, driver: "http" }` and get a scorecard for any restaurant.

---

## Phase 2: Audio-Native Evaluation

### Dependency Graph

```mermaid
graph TD
    PA1["P2-A1<br/>Instrument voice worker<br/>pal-livekit-agent-cloud · 3d"] --> PA2["P2-A2<br/>Receive + store metrics<br/>pal-mono · 1.5d"]
    PA1 --> PB1["P2-B1<br/>Audio evaluators E14–E18<br/>pal-agents + pal-mono · 3d"]
    PA2 --> PB1
    PA1 --> PC1["P2-C1<br/>Voice call simulation<br/>pal-agents + pal-mono · 5d"]

    style PA1 fill:#e8f5e9,stroke:#2e7d32
    style PC1 fill:#fff3e0,stroke:#e65100
    style PA2 fill:#e3f2fd,stroke:#1565c0
    style PB1 fill:#e3f2fd,stroke:#1565c0
```

### Staffing: 2 Engineers, overlapping with Phase 1

```mermaid
gantt
    title Phase 2 - Overlapping with Phase 1
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Engineer B (starts early, pal-livekit-agent-cloud)
    P2-A1 Instrument voice worker               :pa1, 2026-04-14, 3d
    P2-A2 Receive + store audio metrics          :pa2, after pa1, 2d
    P2-B1 Audio evaluators (E14-E18)             :pb1, after pa2, 3d

    section Engineer A (after Phase 1, pal-agents + pal-mono)
    P2-C1 Voice call simulation                  :pc1, after pa1, 5d
    P2-C1 contd (room orchestration + tests)     :pc1b, after pc1, 2d
```

| Day | Engineer A | Engineer B |
|-----|-----------|-----------|
| P1 Day 6-8 | Finishing Phase 1 (C3, F1) | P2-A1 Instrument voice worker (starts early) |
| P2 Day 1-2 | P2-C1 Voice call simulation | P2-A2 Receive + store audio metrics |
| P2 Day 3-5 | P2-C1 continued | P2-B1 Audio evaluators (E14-E18) |
| P2 Day 6-7 | P2-C1 Room orchestration + tests | P2-B1 finishes, review |

**Key optimization**: P2-A1 (instrument voice worker) has zero Phase 1 dependencies — it instruments an existing production service in pal-livekit-agent-cloud. Engineer B starts it on Phase 1 day 6, once their Phase 1 work is done. This saves ~3 calendar days.

**Critical path**: P2-C1 (5d + 2d orchestration). Engineer A starts P2-C1 immediately after Phase 1 completes.

**Phase 2 output**: FDE can run `POST /v1/eval/run { driver: "voice" }` and get a scorecard that includes audio quality metrics (latency, interruptions, STT accuracy).

---

## Phases 3-5: Parallel (2 Engineers)

### Dependency Graph

```mermaid
graph LR
    P3A1["P3-A1<br/>Prod scoring<br/>2d"] --> P3A2["P3-A2<br/>Scores API<br/>1d"]
    P3A1 --> P3B1["P3-B1<br/>Datadog<br/>1d"]
    P3A1 --> P4A1["P4-A1<br/>Anomaly detection<br/>2d"]
    P4A1 --> P4A2["P4-A2<br/>Promote to test<br/>2d"]
    P3A1 --> P5A1["P5-A1<br/>CI gate<br/>2d"]

    style P3A1 fill:#e8f5e9,stroke:#2e7d32
    style P3A2 fill:#e3f2fd,stroke:#1565c0
    style P3B1 fill:#e3f2fd,stroke:#1565c0
    style P5A1 fill:#e3f2fd,stroke:#1565c0
```

### Staffing: 2 Engineers, ~6 Calendar Days

```mermaid
gantt
    title Phases 3-5 - Two Engineers
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Engineer A
    P3-A1 Prod call scoring                     :p3a1, 2026-04-28, 2d
    P4-A1 Anomaly detection + alerting          :p4a1, after p3a1, 2d
    P4-A2 Promote failure to regression test    :p4a2, after p4a1, 2d

    section Engineer B
    (waiting for P3-A1)                         :done, w1, 2026-04-28, 2d
    P3-A2 Scores API                            :p3a2, after w1, 1d
    P3-B1 Datadog quality metrics               :p3b1, after p3a2, 1d
    P5-A1 GitHub Actions eval gate              :p5a1, after p3b1, 2d
```

P3-A2, P3-B1, P4-A1, and P5-A1 all depend only on P3-A1 — not on each other. With 2 engineers, the monitoring track (P4-A1 + P4-A2) runs in parallel with the API/Datadog/CI track (P3-A2 + P3-B1 + P5-A1). Calendar time drops from ~10 days to ~6 days.

---

## Full Timeline (All Phases)

```mermaid
gantt
    title Voice AI Eval Platform - Full Timeline (Max Parallel)
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Phase 1 - Engineer A
    P1-A1 SDK + AgentDriver                     :a1, 2026-04-07, 3d
    P1-C2 Eval service + evaluators             :crit, c2, after a1, 3d
    P1-C3 API routes                            :c3, after c2, 1d
    P1-F1 Batch script                          :f1, after c3, 1d
    Phase 1 complete                            :milestone, after f1, 0d

    section Phase 1 - Engineer B
    P1-B1 Fingerprinting                        :b1, 2026-04-07, 2d
    P1-C1 DB tables                             :c1, 2026-04-07, 2d
    P1-B2 Scenario format                       :b2, after c1, 2d
    P1-E1 Config snapshot                       :e1, after b1, 1d

    section Phase 2 - Engineer B (early start)
    P2-A1 Instrument voice worker               :pa1, 2026-04-14, 3d
    P2-A2 Receive + store metrics               :pa2, after pa1, 2d
    P2-B1 Audio evaluators                      :pb1, after pa2, 3d

    section Phase 2 - Engineer A (after Phase 1)
    P2-C1 Voice call simulation                 :crit, pc1, after f1, 5d
    P2-C1 Room orchestration + tests            :pc1b, after pc1, 2d

    section Phases 3-5 - Engineer A
    P3-A1 Prod call scoring                     :p3a1, after pb1, 2d
    P4-A1 Anomaly detection                     :p4a1, after p3a1, 2d
    P4-A2 Promote to test                       :p4a2, after p4a1, 2d
    All complete                                :milestone, after p4a2, 0d

    section Phases 3-5 - Engineer B
    P3-A2 Scores API                            :p3a2, after p3a1, 1d
    P3-B1 Datadog metrics                       :p3b1, after p3a2, 1d
    P5-A1 GitHub Actions eval gate              :p5a1, after p3b1, 2d
```

---

## Staffing Requirements

| Period | Engineers Needed | What They're Doing |
|--------|-----------------|-------------------|
| **Weeks 1-2** (Phase 1) | **2 backend + 1 frontend** | Backend A: SDK + eval service + API. Backend B: fingerprinting + DB + scenarios. Frontend C: starts UI after API routes ship (day 7). |
| **Weeks 2-4** (Phase 2) | **2 backend + 1 frontend** | Backend A: voice simulation. Backend B: audio instrumentation + evaluators. Frontend C: scorecard views, scenario management. |
| **Weeks 4-5** (Phases 3-5) | **2 backend + 1 frontend** | Backend A+B: prod scoring, monitoring, CI. Frontend C: production quality dashboard, review queue. |

### Which engineers work on which repos?

| Repo | Phase 1 | Phase 2 | Phases 3-5 |
|------|---------|---------|------------|
| **pal-agents** | Backend A (SDK + AgentDriver) | Backend A (SyntheticCaller, VoiceRunner) | — |
| **pal-mono** | Both backends (DB, eval service, API, fingerprinting) | Backend B (audio metrics, evaluators) | Both (scoring, monitoring, CI) |
| **pal-livekit-agent-cloud** | — | Backend B (instrument voice worker) | — |
| **Frontend (admin UI)** | Frontend C (starts week 2) | Frontend C | Frontend C |

---

## UI Workstream (Engineer C — Parallel Track)

Engineer C works entirely on the frontend, building against the API that the backend engineers produce. No backend dependencies block UI work — API schemas are defined in P1-C3 (day 7), and Engineer C can mock responses until the backend is live.

### UI Dependency Chain

```mermaid
graph LR
    C3["P1-C3<br/>API routes ship<br/>(day 7)"] --> U1["UI-1<br/>Eval dashboard shell<br/>+ run trigger"]
    U1 --> U2["UI-2<br/>Scorecard view"]
    U2 --> U3["UI-3<br/>Scenario YAML editor"]
    U3 --> U4["UI-4<br/>Per-conversation<br/>score detail"]
    U4 --> U5["UI-5<br/>Quality dashboard<br/>+ review queue"]

    style C3 fill:#e8f5e9,stroke:#2e7d32
    style U1 fill:#f3e5f5,stroke:#6a1b9a
    style U2 fill:#f3e5f5,stroke:#6a1b9a
    style U3 fill:#f3e5f5,stroke:#6a1b9a
    style U4 fill:#f3e5f5,stroke:#6a1b9a
    style U5 fill:#f3e5f5,stroke:#6a1b9a
```

### UI Tasks

| Task | What FDE Sees | Effort | API Dependency | Ships With |
|------|--------------|--------|----------------|------------|
| **UI-1** Eval dashboard + run trigger | "Run eval" button per restaurant. Shows run history (status, score, date). | 2d | `POST /v1/eval/run`, `GET /v1/eval/runs/{run_id}` | Phase 1 |
| **UI-2** Scorecard view | Per-restaurant scorecard: pass/fail per evaluator per scenario. Go/no-go recommendation. Drill into failure reasons. | 3d | `GET /v1/eval/scorecard/{project_id}` | Phase 1 |
| **UI-3** Scenario editor | View/import/edit YAML scenarios per restaurant. Syntax highlighting. Validation errors. | 2d | Scenario CRUD endpoints (if added) or file-based | Phase 1 |
| **UI-4** Per-conversation score detail | Click a production call → see all evaluator scores, judge reasoning, tool calls, transcript. | 2d | `GET /v1/eval/conversation/{id}/scores` | Phase 3 |
| **UI-5** Quality dashboard + review queue | Per-account quality trends over time. Flagged calls. Review workflow (false positive / systemic / needs fix). | 3d | Datadog embed or custom charts + review queue API | Phase 4 |

### UI Gantt (Engineer C)

```mermaid
gantt
    title UI Workstream — Engineer C (Parallel)
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Blocked (waiting for API)
    API schema review + mock setup              :done, u0, 2026-04-07, 5d

    section Phase 1 UI
    UI-1 Eval dashboard + run trigger           :u1, 2026-04-14, 2d
    UI-2 Scorecard view                         :u2, after u1, 3d
    UI-3 Scenario editor                        :u3, after u2, 2d

    section Phase 3-4 UI
    UI-4 Per-conversation score detail          :u4, after u3, 2d
    UI-5 Quality dashboard + review queue       :u5, after u4, 3d
```

**Week 1 (days 1–5)**: Engineer C reviews API schemas from P1-C3, sets up mock responses, builds component scaffolding. Not blocked — can work from the request/response schemas before the backend is live.

**Week 2 (days 6–10)**: UI-1 (run trigger + history) and UI-2 (scorecard) ship. FDEs can trigger evals and read results from a UI instead of curl.

**Week 3 (days 11–15)**: UI-3 (scenario editor) ships. FDEs can view and edit scenarios from the UI.

**Weeks 4–5**: UI-4 (per-conversation detail) and UI-5 (quality dashboard + review queue) ship alongside Phases 3–4 backend.

### What FDEs See at Each Milestone

| Milestone | Without UI (API/CLI only) | With UI (Engineer C) |
|---|---|---|
| **Phase 1 complete** | `curl POST /v1/eval/run` + `curl GET /v1/eval/scorecard/...` | "Run Eval" button, scorecard page with pass/fail per scenario, scenario editor |
| **Phase 2 complete** | Same API, now with audio metrics in JSON response | Audio metrics displayed in scorecard (latency, interruptions, STT accuracy) |
| **Phase 3 complete** | `curl GET /v1/eval/conversation/{id}/scores` | Click any production call → see all scores + judge reasoning |
| **Phase 4 complete** | Slack alerts + JSON API for review queue | Quality trends dashboard, review queue workflow in UI |

---

## What Ships When

| Milestone | Date (est.) | What FDEs/Team Can Do |
|-----------|------------|----------------------|
| **Phase 1 complete** | End of Week 2 | Run `POST /v1/eval/run { driver: "http" }` for any restaurant. Get a scorecard. Go/no-go for onboarding. Batch regression across all customers. |
| **P2-A1 done** (voice instrumented) | Week 2 | Every production call now captures per-turn latencies, interruption events, and dual-channel recording. Visible in Datadog. |
| **P2-C1 done** (voice simulation) | Week 3 | Run `POST /v1/eval/run { driver: "voice" }` — synthetic caller places a real voice call to the agent via LiveKit. Tests STT, TTS, turn-taking. |
| **Phase 2 complete** | End of Week 4 | Full audio scorecard: latency, interruptions, STT accuracy, speech rate, silence gaps — alongside transcript-level evaluators. |
| **Phases 3-5 complete** | End of Week 5 | Every production call scored. Datadog metrics. Anomaly alerting. Failed calls auto-promoted to regression tests. PRs blocked if quality regresses > 5%. |

---

## Risks to Timeline

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LiveKit `lk.agent.state` attribute not reliable for turn detection | P2-C1 takes longer (need Silero VAD fallback) | Build VAD fallback from day 1. Budget 1 extra day. |
| AgentDispatch API doesn't work as expected for test rooms | P2-C1 blocked | Validate in week 1 with a manual test before committing to the architecture. |
| pal-agents SDK extraction breaks existing eval scripts | P1-A1 takes longer | Acceptance criteria requires existing scripts still work. Run them as part of the PR. |
| LLM judge costs higher than expected | No timeline impact, budget impact | Start with gpt-4o-mini. Monitor cost per eval run in Phase 1. |
| FDE scenario authoring slower than expected | Phase 1 usable but fewer scenarios | Ship with 10 generic scenarios. FDE-authored scenarios grow over time. |
| Dual-channel recording breaks downstream consumers | P2-A1 requires coordination | Check with team before switching. Can run both formats in parallel during transition. |
