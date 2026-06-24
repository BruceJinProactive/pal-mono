from __future__ import annotations

import copy
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_SMOOTHING_METADATA_KEY = "smoothing"
_OBSERVATIONS_KEY = "observations"
_FINALIZED_OBSERVED_AT_KEY = "finalized_observed_at"
_DEFAULT_FRAME_INTERVAL_SECONDS = 15
_DEFAULT_MAX_FRAME_GAP_SECONDS = 3600
_DEFAULT_RETENTION_FRAMES = 7


@dataclass(frozen=True)
class EventGenerationConfig:
    strategy: str
    window_frames: int
    frame_interval_seconds: int
    max_frame_gap_seconds: int
    retention_frames: int


@dataclass(frozen=True)
class SmoothingObservation:
    observed_at: datetime
    state_id: uuid.UUID
    state: str
    confidence: float
    frame_s3_key: str | None
    camera_config_id: uuid.UUID


@dataclass(frozen=True)
class SmoothingDecision:
    center_observed_at: datetime
    center_frame_s3_key: str | None
    center_camera_config_id: uuid.UUID
    state_id: uuid.UUID | None
    state: str | None
    confidence: float | None
    metadata: dict[str, Any]


def single_frame_event_generation_config() -> EventGenerationConfig:
    return EventGenerationConfig(
        strategy="single_frame",
        window_frames=1,
        frame_interval_seconds=_DEFAULT_FRAME_INTERVAL_SECONDS,
        max_frame_gap_seconds=_DEFAULT_MAX_FRAME_GAP_SECONDS,
        retention_frames=_DEFAULT_RETENTION_FRAMES,
    )


def parse_event_generation_config(
    value: object,
) -> EventGenerationConfig:
    if not isinstance(value, dict):
        return single_frame_event_generation_config()

    strategy = value.get("strategy")
    if strategy != "centered_majority_vote":
        return single_frame_event_generation_config()

    window_frames = _positive_int(value.get("window_frames"), default=5)
    if window_frames not in {3, 5}:
        window_frames = 5

    frame_interval_seconds = _positive_int(
        value.get("frame_interval_seconds"),
        default=_DEFAULT_FRAME_INTERVAL_SECONDS,
    )
    max_frame_gap_seconds = _positive_int(
        value.get("max_frame_gap_seconds"),
        default=max(_DEFAULT_MAX_FRAME_GAP_SECONDS, frame_interval_seconds * 4),
    )
    retention_frames = max(
        _positive_int(value.get("retention_frames"), default=_DEFAULT_RETENTION_FRAMES),
        window_frames + 2,
    )

    return EventGenerationConfig(
        strategy="centered_majority_vote",
        window_frames=window_frames,
        frame_interval_seconds=frame_interval_seconds,
        max_frame_gap_seconds=max_frame_gap_seconds,
        retention_frames=retention_frames,
    )


def is_smoothing_enabled(config: EventGenerationConfig) -> bool:
    return config.strategy == "centered_majority_vote" and config.window_frames in {
        3,
        5,
    }


def append_smoothing_observation(
    entity_metadata: dict[str, object],
    definition_type: str,
    observation: SmoothingObservation,
    config: EventGenerationConfig,
) -> dict[str, object]:
    metadata = copy.deepcopy(entity_metadata)
    smoothing = _metadata_dict(metadata, _SMOOTHING_METADATA_KEY)
    bucket = _metadata_dict(smoothing, definition_type)
    rows = _observation_rows(bucket)

    serialized = _serialize_observation(observation)
    rows = [row for row in rows if not _same_observation(row, serialized)]
    rows.append(serialized)
    rows.sort(
        key=lambda row: _parse_datetime(row.get("observed_at"))
        or datetime.min.replace(tzinfo=timezone.utc)
    )
    rows = _contiguous_tail(rows, config.max_frame_gap_seconds)
    rows = rows[-config.retention_frames :]

    bucket[_OBSERVATIONS_KEY] = rows
    return metadata


def collect_ready_smoothing_decisions(
    entity_metadata: dict[str, object],
    definition_type: str,
    config: EventGenerationConfig,
    _now: datetime,
) -> list[SmoothingDecision]:
    smoothing = entity_metadata.get(_SMOOTHING_METADATA_KEY)
    if not isinstance(smoothing, dict):
        return []
    bucket = smoothing.get(definition_type)
    if not isinstance(bucket, dict):
        return []

    rows = _observation_rows(bucket)
    finalized_at = _parse_datetime(bucket.get(_FINALIZED_OBSERVED_AT_KEY))
    observations = [_deserialize_observation(row) for row in rows]
    observations = [obs for obs in observations if obs is not None]
    observations.sort(key=lambda obs: obs.observed_at)

    radius = config.window_frames // 2
    decisions: list[SmoothingDecision] = []
    for index, center in enumerate(observations):
        if finalized_at is not None and center.observed_at <= finalized_at:
            continue
        if not _can_finalize(index, len(observations), radius):
            break
        window_start = max(0, index - radius)
        window_end = min(len(observations), index + radius + 1)
        decision = _vote_window(
            center=center,
            window=observations[window_start:window_end],
            config=config,
        )
        decisions.append(decision)

    return decisions


def mark_smoothing_finalized(
    entity_metadata: dict[str, object],
    definition_type: str,
    observed_at: datetime,
) -> dict[str, object]:
    metadata = copy.deepcopy(entity_metadata)
    smoothing = _metadata_dict(metadata, _SMOOTHING_METADATA_KEY)
    bucket = _metadata_dict(smoothing, definition_type)
    bucket[_FINALIZED_OBSERVED_AT_KEY] = _format_datetime(observed_at)
    return metadata


def build_smoothing_metadata(
    definition_type: str,
    observations: list[dict[str, object]],
    finalized_observed_at: str | None = None,
) -> dict[str, object]:
    bucket: dict[str, object] = {_OBSERVATIONS_KEY: observations}
    if finalized_observed_at is not None:
        bucket[_FINALIZED_OBSERVED_AT_KEY] = finalized_observed_at
    return {_SMOOTHING_METADATA_KEY: {definition_type: bucket}}


def smoothing_observation_rows(
    entity_metadata: dict[str, object],
    definition_type: str,
) -> list[dict[str, object]]:
    smoothing = entity_metadata.get(_SMOOTHING_METADATA_KEY)
    if not isinstance(smoothing, dict):
        return []
    bucket = smoothing.get(definition_type)
    if not isinstance(bucket, Mapping):
        return []
    return _observation_rows(bucket)


def smoothing_finalized_observed_at(
    entity_metadata: dict[str, object],
    definition_type: str,
) -> str | None:
    smoothing = entity_metadata.get(_SMOOTHING_METADATA_KEY)
    if not isinstance(smoothing, dict):
        return None
    bucket = smoothing.get(definition_type)
    if not isinstance(bucket, Mapping):
        return None
    value = bucket.get(_FINALIZED_OBSERVED_AT_KEY)
    return value if isinstance(value, str) else None


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default


def _metadata_dict(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    new_value: dict[str, object] = {}
    parent[key] = new_value
    return new_value


def _observation_rows(bucket: Mapping[str, object]) -> list[dict[str, object]]:
    value = bucket.get(_OBSERVATIONS_KEY)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _serialize_observation(observation: SmoothingObservation) -> dict[str, object]:
    return {
        "observed_at": _format_datetime(observation.observed_at),
        "state_id": str(observation.state_id),
        "state": observation.state,
        "confidence": observation.confidence,
        "frame_s3_key": observation.frame_s3_key,
        "camera_config_id": str(observation.camera_config_id),
    }


def _deserialize_observation(row: dict[str, object]) -> SmoothingObservation | None:
    observed_at = _parse_datetime(row.get("observed_at"))
    state_id = _parse_uuid(row.get("state_id"))
    state = row.get("state")
    confidence = row.get("confidence")
    camera_config_id = _parse_uuid(row.get("camera_config_id"))
    if (
        observed_at is None
        or state_id is None
        or not isinstance(state, str)
        or camera_config_id is None
    ):
        return None

    frame_s3_key = row.get("frame_s3_key")
    return SmoothingObservation(
        observed_at=observed_at,
        state_id=state_id,
        state=state,
        confidence=float(confidence) if isinstance(confidence, int | float) else 0.0,
        frame_s3_key=frame_s3_key if isinstance(frame_s3_key, str) else None,
        camera_config_id=camera_config_id,
    )


def _same_observation(
    left: dict[str, object],
    right: dict[str, object],
) -> bool:
    left_observed_at = left.get("observed_at")
    right_observed_at = right.get("observed_at")
    if isinstance(left_observed_at, str) and isinstance(right_observed_at, str):
        return left_observed_at == right_observed_at

    left_frame = left.get("frame_s3_key")
    right_frame = right.get("frame_s3_key")
    if isinstance(left_frame, str) and isinstance(right_frame, str):
        return left_frame == right_frame
    return False


def _contiguous_tail(
    rows: list[dict[str, object]],
    max_frame_gap_seconds: int,
) -> list[dict[str, object]]:
    if len(rows) < 2:
        return rows

    start_index = 0
    previous = _parse_datetime(rows[0].get("observed_at"))
    for index, row in enumerate(rows[1:], start=1):
        current = _parse_datetime(row.get("observed_at"))
        if previous is not None and current is not None:
            gap_seconds = (current - previous).total_seconds()
            if gap_seconds > max_frame_gap_seconds:
                start_index = index
        previous = current
    return rows[start_index:]


def _can_finalize(
    index: int,
    total: int,
    radius: int,
) -> bool:
    has_full_window = index - radius >= 0 and index + radius < total
    if has_full_window:
        return True

    has_start_boundary_window = index < radius and index + radius < total
    return has_start_boundary_window


def _vote_window(
    center: SmoothingObservation,
    window: list[SmoothingObservation],
    config: EventGenerationConfig,
) -> SmoothingDecision:
    counts = Counter(str(obs.state_id) for obs in window)
    required_votes = len(window) // 2 + 1
    winning_state_id: uuid.UUID | None = None
    winning_state: str | None = None
    winning_confidence: float | None = None

    if len(window) >= 2 and counts:
        top_count = max(counts.values())
        top_state_ids = [
            state_id for state_id, count in counts.items() if count == top_count
        ]
        if top_count >= required_votes and len(top_state_ids) == 1:
            winning_state_id = uuid.UUID(top_state_ids[0])
            winning_observations = [
                obs for obs in window if obs.state_id == winning_state_id
            ]
            winning_state = winning_observations[-1].state
            winning_confidence = sum(
                obs.confidence for obs in winning_observations
            ) / len(winning_observations)

    return SmoothingDecision(
        center_observed_at=center.observed_at,
        center_frame_s3_key=center.frame_s3_key,
        center_camera_config_id=center.camera_config_id,
        state_id=winning_state_id,
        state=winning_state,
        confidence=winning_confidence,
        metadata={
            "strategy": config.strategy,
            "window_frames": config.window_frames,
            "required_votes": required_votes,
            "center_observed_at": _format_datetime(center.observed_at),
            "center_frame_s3_key": center.frame_s3_key,
            "center_camera_config_id": str(center.camera_config_id),
            "vote_counts": dict(counts),
            "observations": [
                {
                    "observed_at": _format_datetime(obs.observed_at),
                    "state_id": str(obs.state_id),
                    "state": obs.state,
                    "confidence": obs.confidence,
                    "frame_s3_key": obs.frame_s3_key,
                    "camera_config_id": str(obs.camera_config_id),
                }
                for obs in window
            ],
        },
    )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str):
        return None
    raw_value = value.strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        return _as_utc(datetime.fromisoformat(raw_value))
    except ValueError:
        return None


def _parse_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _format_datetime(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
