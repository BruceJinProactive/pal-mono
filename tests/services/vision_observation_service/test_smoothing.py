from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from services.vision_observation_service._smoothing import (
    EventGenerationConfig,
    SmoothingObservation,
    append_smoothing_observation,
    collect_ready_smoothing_decisions,
    parse_event_generation_config,
)


def _config(window_frames: int = 5) -> EventGenerationConfig:
    return parse_event_generation_config(
        {
            "strategy": "centered_majority_vote",
            "window_frames": window_frames,
            "frame_interval_seconds": 15,
            "max_frame_gap_seconds": 3600,
        }
    )


def _observation(
    observed_at: datetime,
    state_id: uuid.UUID,
    state: str,
    frame_s3_key: str,
    camera_config_id: uuid.UUID | None = None,
) -> SmoothingObservation:
    return SmoothingObservation(
        observed_at=observed_at,
        state_id=state_id,
        state=state,
        frame_s3_key=frame_s3_key,
        camera_config_id=camera_config_id or uuid.uuid4(),
    )


def test_five_frame_window_uses_three_of_five_majority() -> None:
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {}
    config = _config(window_frames=5)

    states = [
        (dirty_id, "dirty"),
        (clean_id, "clean"),
        (dirty_id, "dirty"),
        (dirty_id, "dirty"),
        (clean_id, "clean"),
    ]
    for index, (state_id, state) in enumerate(states):
        observed_at = start + timedelta(seconds=index * 15)
        metadata = append_smoothing_observation(
            metadata,
            "cleanliness",
            _observation(observed_at, state_id, state, f"frame-{index}.jpg"),
            config,
        )

    decisions = collect_ready_smoothing_decisions(
        metadata,
        "cleanliness",
        config,
        start + timedelta(seconds=60),
    )

    center_decision = next(
        decision
        for decision in decisions
        if decision.center_observed_at == start + timedelta(seconds=30)
    )
    assert center_decision.state_id == dirty_id
    assert center_decision.state == "dirty"
    assert center_decision.metadata["required_votes"] == 3
    assert center_decision.metadata["vote_counts"][str(dirty_id)] == 3


def test_decision_uses_center_observation_camera() -> None:
    dirty_id = uuid.uuid4()
    center_camera_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {}
    config = _config(window_frames=3)

    for index, camera_config_id in enumerate(
        [uuid.uuid4(), center_camera_id, uuid.uuid4()]
    ):
        metadata = append_smoothing_observation(
            metadata,
            "cleanliness",
            _observation(
                start + timedelta(seconds=index * 15),
                dirty_id,
                "dirty",
                f"frame-{index}.jpg",
                camera_config_id=camera_config_id,
            ),
            config,
        )

    decisions = collect_ready_smoothing_decisions(
        metadata,
        "cleanliness",
        config,
        start + timedelta(seconds=45),
    )
    center_decision = next(
        decision
        for decision in decisions
        if decision.center_observed_at == start + timedelta(seconds=15)
    )

    assert center_decision.center_camera_config_id == center_camera_id
    assert center_decision.metadata["center_camera_config_id"] == str(center_camera_id)


def test_start_of_session_partial_window_finalizes_first_frame() -> None:
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {}
    config = _config(window_frames=5)

    for index, state_id in enumerate([dirty_id, dirty_id, clean_id]):
        metadata = append_smoothing_observation(
            metadata,
            "cleanliness",
            _observation(
                start + timedelta(seconds=index * 15),
                state_id,
                "dirty" if state_id == dirty_id else "clean",
                f"frame-{index}.jpg",
            ),
            config,
        )

    decisions = collect_ready_smoothing_decisions(
        metadata,
        "cleanliness",
        config,
        start + timedelta(seconds=30),
    )

    assert decisions[0].center_observed_at == start
    assert decisions[0].state_id == dirty_id
    assert decisions[0].metadata["required_votes"] == 2


def test_tail_window_does_not_finalize_without_future_neighbors() -> None:
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {}
    config = _config(window_frames=5)

    for index, state_id in enumerate([dirty_id, dirty_id, clean_id, dirty_id]):
        metadata = append_smoothing_observation(
            metadata,
            "cleanliness",
            _observation(
                start + timedelta(seconds=index * 15),
                state_id,
                "dirty" if state_id == dirty_id else "clean",
                f"frame-{index}.jpg",
            ),
            config,
        )

    decisions = collect_ready_smoothing_decisions(
        metadata,
        "cleanliness",
        config,
        start + timedelta(seconds=90),
    )

    assert [decision.center_observed_at for decision in decisions] == [
        start,
        start + timedelta(seconds=15),
    ]


def test_max_gap_discards_previous_session_observations() -> None:
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    previous_session = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    current_session = previous_session + timedelta(hours=1, seconds=1)
    metadata: dict[str, object] = {}
    config = _config(window_frames=5)

    metadata = append_smoothing_observation(
        metadata,
        "cleanliness",
        _observation(previous_session, dirty_id, "dirty", "previous.jpg"),
        config,
    )
    metadata = append_smoothing_observation(
        metadata,
        "cleanliness",
        _observation(current_session, clean_id, "clean", "current.jpg"),
        config,
    )

    smoothing = metadata["smoothing"]
    assert isinstance(smoothing, dict)
    bucket = smoothing["cleanliness"]
    assert isinstance(bucket, dict)
    observations = bucket["observations"]
    assert isinstance(observations, list)
    assert len(observations) == 1
    assert observations[0]["frame_s3_key"] == "current.jpg"


def test_same_frame_replaces_prior_observation_for_idempotency() -> None:
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    observed_at = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {}
    config = _config(window_frames=3)

    metadata = append_smoothing_observation(
        metadata,
        "cleanliness",
        _observation(observed_at, dirty_id, "dirty", "frame.jpg"),
        config,
    )
    metadata = append_smoothing_observation(
        metadata,
        "cleanliness",
        _observation(observed_at, clean_id, "clean", "frame.jpg"),
        config,
    )

    smoothing = metadata["smoothing"]
    assert isinstance(smoothing, dict)
    bucket = smoothing["cleanliness"]
    assert isinstance(bucket, dict)
    observations = bucket["observations"]
    assert isinstance(observations, list)
    assert len(observations) == 1
    assert observations[0]["state"] == "clean"


def test_same_video_key_keeps_distinct_observed_at_frames() -> None:
    dirty_id = uuid.uuid4()
    clean_id = uuid.uuid4()
    start = datetime(2026, 6, 19, 9, 0, tzinfo=timezone.utc)
    metadata: dict[str, object] = {}
    config = _config(window_frames=5)

    for index, state_id in enumerate([dirty_id, clean_id, dirty_id]):
        metadata = append_smoothing_observation(
            metadata,
            "cleanliness",
            _observation(
                start + timedelta(seconds=index * 15),
                state_id,
                "dirty" if state_id == dirty_id else "clean",
                "security/cameras/account/project/cam/videos/2026-06-19/source.mkv",
            ),
            config,
        )

    smoothing = metadata["smoothing"]
    assert isinstance(smoothing, dict)
    bucket = smoothing["cleanliness"]
    assert isinstance(bucket, dict)
    observations = bucket["observations"]
    assert isinstance(observations, list)
    assert len(observations) == 3
    assert [row["observed_at"] for row in observations] == [
        "2026-06-19T09:00:00+00:00",
        "2026-06-19T09:00:15+00:00",
        "2026-06-19T09:00:30+00:00",
    ]
