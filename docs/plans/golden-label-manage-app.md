# Plan: Add Voting and Hysteresis to Vision V2 Event Generation

**Status:** Planning
**Created:** 2026-05-26

---

## Context

Vision v2 event generation currently needs a more stable transition policy for
frame-by-frame observations. A single noisy frame should not immediately flip an
entity state or fire an event.

The event setup flow should support last-N-frame voting with hysteresis. When an
event is configured this way, the current state remains sticky until another
state has overwhelming support in the recent frame window.

Golden labeling remains a manual `pal-research` workflow used for evaluation and
calibration. See [Vision Golden Labeling](../state/vision-golden-labeling.md).

---

## Objective

Add an event-generation strategy that:

1. Samples frames at a configurable cadence. Default: one frame every 1 second.
2. Keeps the last N frame observations for each configured event/entity.
3. Defaults N to 5 when last-N voting is enabled.
4. Keeps the current state unless another state appears with overwhelming
  support in the recent window.
5. Treats "overwhelming" as a configurable threshold above simple majority,
  defaulting to 0.8. A value of 0.75 should also be supported.
6. Creates a state-change event only when the candidate state crosses that
  threshold.

Example:

- Current state: `A`
- Last 5 frame votes: `B, B, B, B, A`
- Threshold: `0.8`
- Result: switch to `B` and create one event

Counterexample:

- Current state: `A`
- Last 5 frame votes: `B, B, B, A, A`
- Threshold: `0.8`
- Result: stay in `A`; no state-change event

---

## Concepts


| Term              | Meaning                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| Frame observation | The LLM output for one processed camera frame and one entity/event.                    |
| Frame interval    | Seconds between extracted/analyzed frames. Default: 1 second.                          |
| Current state     | The persisted state we currently believe the entity/event is in.                       |
| Candidate state   | The non-current state with the highest vote count in the recent window.                |
| Voting window     | The most recent N valid frame observations. Default: 5 frames.                         |
| Switch threshold  | Fraction of the window required before changing state. Default: 0.8.                   |
| Hysteresis        | The current state remains sticky until a candidate state crosses the switch threshold. |


Hysteresis here is not the offline "merge short gaps" post-processing used by
the research scripts. In production event generation, hysteresis is the rule
that state `A` holds until state `B` has overwhelming recent evidence.

---

## Proposed Configuration

Add an event-generation block to the v2 event definition. If the v2 event
definition is represented by `vision_rule`, store this initially in
`vision_rule.rule_metadata` to avoid a schema migration:

```json
{
  "event_generation": {
    "version": 2,
    "strategy": "last_n_vote",
    "frame_interval_seconds": 1,
    "vote_window_frames": 5,
    "switch_threshold": 0.8,
    "min_confidence": null,
    "ignore_irrelevant_frames": true
  }
}
```

Supported strategies:


| Strategy       | Behavior                                                             |
| -------------- | -------------------------------------------------------------------- |
| `single_frame` | Default rollout behavior: a single frame can trigger a state change. |
| `last_n_vote`  | Opt-in behavior: switch only when recent votes exceed the threshold. |


Validation rules:

- `strategy` defaults to `single_frame`. Events can opt into `last_n_vote`
later without changing the default rollout behavior.
- `frame_interval_seconds` defaults to 1 and must be at least 1. The current
v2 cadence of roughly one frame every 10 seconds is too sparse for useful
last-5-frame voting in most fast-changing scenes.
- `vote_window_frames` defaults to 5 and must be at least 1.
- `switch_threshold` defaults to 0.8 and must be greater than 0.5 and less than
or equal to 1.0.
- The required vote count is `ceil(vote_window_frames * switch_threshold)`.
- Frames with `state_id = null` should not count as votes.
- If `ignore_irrelevant_frames` is true, irrelevant images should not count as
votes.
- If `min_confidence` is set, observations below that confidence should not
count as votes.
- Partial warm-up windows should not switch state unless the candidate already
meets the required vote count for the configured full window.

Defaults can be global, but the effective values should be event-specific. Each
event can override the global defaults for frame cadence, voting window,
threshold, and confidence filter.

---

## State and Observation Storage

Last-N voting needs access to recent frame observations. The current
`vision_state_change_event` table records transitions, not every observation, so
it is not enough by itself.

Preferred implementation:

Create a small append-only observation history table, tentatively named
`vision_entity_observation`.

Suggested columns:


| Column              | Purpose                                                        |
| ------------------- | -------------------------------------------------------------- |
| `id`                | Observation ID                                                 |
| `camera_config_id`  | Camera configuration that produced the observation             |
| `entity_id`         | Observed entity                                                |
| `observed_state_id` | State selected by the LLM                                      |
| `confidence`        | LLM confidence for the selected state                          |
| `frame_s3_key`      | Frame that produced the observation, if retained directly      |
| `observed_at`       | Observation timestamp, required for S3 frame lookup/extraction |
| `metadata`          | Raw vote/debug metadata                                        |


Suggested index:

```text
(camera_config_id, entity_id, observed_at DESC)
```

Retain at least 7 days of observation history for debugging. We should also keep
raw frames for at least that window, or make frame extraction from S3
straightforward. If we choose S3 extraction instead of retaining every raw frame
key, the table still needs `observed_at` so we can locate the source frame by
camera and timestamp.

Short-term alternative:

Store a rolling window in `vision_entity.metadata`. This avoids a migration, but
it is weaker for concurrency, debugging, and cross-worker consistency. Use this
only if we need a very small experiment before adding the observation table.

---

## Event Generation Algorithm

For each frame observation:

1. Persist the observation, unless it is invalid or intentionally ignored.
2. Load the current state for the entity/event.
3. Load the most recent `vote_window_frames` valid observations.
4. Count votes by `observed_state_id`.
5. Find the top candidate state.
6. If there is no current state, initialize with a simple majority of the recent
  valid window. Initial state does not need the overwhelming threshold because
   future events can correct it.
7. If the candidate is the current state, do nothing.
8. If the candidate is different from the current state and
  `candidate_votes >= ceil(vote_window_frames * switch_threshold)`, switch:
  - update `vision_entity.current_state_id`
  - update `vision_entity.current_state_since`
  - create `vision_state_change_event`
  - include vote-window debug data in `event_metadata`
9. Otherwise, leave the current state unchanged.

Pseudocode:

```python
valid_votes = recent_valid_observations[-window_size:]
counts = Counter(vote.observed_state_id for vote in valid_votes)
candidate_state_id, candidate_count = counts.most_common(1)[0]

if current_state_id is None:
    required_votes = floor(len(valid_votes) / 2) + 1
else:
    required_votes = ceil(window_size * switch_threshold)

if candidate_state_id != current_state_id and candidate_count >= required_votes:
    switch_state(candidate_state_id)
```

For the default `window_size = 5` and `switch_threshold = 0.8`, a switch requires
4 of the last 5 valid frames to agree after initialization. Initial state only
requires a simple majority of the available recent valid observations.

---

## Event Metadata

When a switch happens, store enough metadata to explain why:

```json
{
  "event_generation": {
    "strategy": "last_n_vote",
    "vote_window_frames": 5,
    "switch_threshold": 0.8,
    "required_votes": 4,
    "candidate_votes": 4,
    "vote_counts": {
      "state-b-id": 4,
      "state-a-id": 1
    },
    "frame_s3_keys": [
      "cameras/cam-1/frame-001.jpg",
      "cameras/cam-1/frame-002.jpg"
    ]
  }
}
```

This makes state changes auditable from the existing state-change event list and
gives golden-label evaluation a clear production trace to compare against.

---

## Implementation Phases

### Phase 1: Backend Algorithm

- Add a pure helper for voting and hysteresis decisions.
- Unit test edge cases:
  - 4/5 votes switches at threshold 0.8
  - 3/5 votes does not switch at threshold 0.8
  - current-state votes do not create duplicate events
  - invalid or low-confidence frames are excluded
  - empty or partial windows do not switch prematurely
- Keep the helper independent of FastAPI and SQLAlchemy so it is easy to test.

### Phase 2: Observation History

- Add durable storage for recent frame observations.
- Query the most recent N valid observations by camera config and entity.
- Retain at least 7 days of observations and raw-frame access for debugging.
- Add cleanup or partition-retention handling after the 7-day debugging window.

### Phase 3: Wire Into V2 Event Generation

- Replace the immediate single-frame state switch path with a strategy lookup.
- Keep `single_frame` as the backwards-compatible default unless the event
explicitly enables `last_n_vote`.
- When `last_n_vote` is enabled, call the voting helper before updating entity
state or creating `vision_state_change_event`.
- Store vote-window metadata on generated state-change events.

### Phase 4: Manage App Setup Controls

In the v2 event setup UI, expose only the event-generation settings:

- Strategy: single frame or last-N vote
- Frame interval: default 1 second
- Window size: default 5
- Switch threshold: default 80%, with 75% available
- Optional minimum confidence

Golden-label proposal, editing, approval, and GitHub commit flows remain outside
the manage app for this plan.

### Phase 5: Evaluation With Golden Labels

- Keep using `pal-research` goldens to evaluate the production event-generation
behavior.
- Compare generated state-change intervals against manually verified golden
intervals.
- Use the vote metadata to debug false positives and missed transitions.

---

## Out of Scope

- Moving `propose_golden.py`, `golden_frame.py`, `golden_bbox.py`, or
`accuracy.py` into pal-mono.
- Building a golden-label editor in the manage app.
- Storing verified golden labels in the pal-mono database.
- Committing golden JSON files to GitHub from pal-mono.
- Automatically approving model-generated labels as golden data.

---

## Open Questions

1. Is the v2 event definition definitely `vision_rule`, or is there a separate
  v2 event model outside this repo that should own the config?
2. Should observation history be a new table immediately, or should we run a
  short experiment using `vision_entity.metadata` as a rolling window?
3. Do we retain raw frame objects directly for 7 days, or retain enough camera
  and timestamp metadata to regenerate/extract the frame from S3?

