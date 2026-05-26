# Vision Golden Labeling

**Last updated:** 2026-05-26

Golden labeling is the manual research workflow for creating verified reference
intervals for vision events. It stays in `pal-research`; pal-mono should consume
the resulting knowledge for evaluation, but should not own the labeling tool.

---

## Purpose

Golden labels answer: "What actually happened in this camera clip?"

They are used to measure whether a prompt, model, frame interval, or production
event-generation strategy is accurate. They should be reviewed by a human before
being treated as ground truth.

---

## Where the Tools Live

The current tooling is in `pal-research/tools/`:

| Tool | Purpose |
| --- | --- |
| `propose_golden.py` | Runs multiple whole-video Gemini tries and majority-votes intervals. |
| `golden_frame.py` | Extracts frames, runs multiple tries per frame, and produces per-frame probabilities. |
| `golden_bbox.py` | Bounding-box/crop variant for region-specific checks. |
| `explain_frame.py` | Runs frame explanation prompts and aggregates explanations/probabilities for debugging. |
| `accuracy.py` | Compares predictions against verified golden intervals. |

Related references:

- `pal-research/agent/README.md` documents the golden reference JSON shape.
- `pal-research/poc/ANALYSIS_EXAMPLE.md` documents comparison and tolerance
  behavior.
- Prompts live under `pal-research/agent/prompts/`.

---

## Manual Workflow

1. Collect representative clips for one camera and event.
   - Prefer multiple one-minute clips from the same camera.
   - Keep filenames stable so prediction and golden files can be matched later.
2. Pick the prompt that matches the event.
   - Frame prompts generally end in `_frame.md`.
   - Whole-video prompts omit that suffix.
3. Run a proposal tool.
   - Use `propose_golden.py` for whole-video interval proposals.
   - Use `golden_frame.py` for frame-level proposals and probabilities.
   - Use `explain_frame.py` when the label needs explanation evidence or bbox
     debugging.
4. Review the output manually.
   - Watch the clip around each transition.
   - Correct start/end times.
   - Remove hallucinated intervals.
   - Add missed intervals.
5. Save the verified JSON in the relevant `pal-research` location.
6. Use `accuracy.py` to compare candidate predictions against the verified
   golden file.
7. Commit the verified golden data through the normal `pal-research` review
   process.

---

## Golden File Shape

The common golden reference shape is:

```json
{
  "event_name": "cashier-monitoring",
  "video_list": [
    {
      "video_path": "2026-05-01_15-49-09.mp4",
      "interval_list": [
        {
          "status": "present",
          "start": 0,
          "end": 15
        }
      ]
    }
  ]
}
```

Field notes:

| Field | Meaning |
| --- | --- |
| `event_name` | Human-readable event identifier. |
| `video_path` | Stable path or filename used to match predictions to goldens. |
| `interval_list` | Verified intervals for the event. |
| `status` | Event state during the interval. |
| `start` / `end` | Relative time in seconds. |

Some tools accept variants, but this shape is the easiest one to maintain.

---

## Tool Behavior

`propose_golden.py`:

- Uploads a video once.
- Runs N parallel model tries.
- Parses `interval_list` JSON from each try.
- Keeps seconds where a strict majority of tries agree.
- Merges consecutive kept seconds into intervals.

`golden_frame.py`:

- Extracts frames from video.
- Uploads frames in parallel.
- Runs M model tries per frame.
- Computes probability as `vote_count / tries_per_frame`.
- Can emit binary intervals after filtering probabilities above 0.5.

`accuracy.py`:

- Normalizes predicted and golden intervals.
- Compares second-by-second status.
- Applies transition tolerance when configured.
- Reports diff percentage and cost estimates.

`explain_frame.py`:

- Uploads one or more frames once.
- Runs N Gemini explanation queries per frame.
- Aggregates event probability by `(status, entity)`.
- Keeps explanations and optional visual overlays for manual debugging.

---

## Relationship to Production Event Generation

Golden labeling and production event generation are separate:

- Golden labeling is manual ground-truth creation.
- Production event generation runs on live camera frames and may use last-N
  voting plus hysteresis to avoid noisy state flips.

Use golden files to evaluate the production strategy, but keep the golden label
authoring process in `pal-research`.
