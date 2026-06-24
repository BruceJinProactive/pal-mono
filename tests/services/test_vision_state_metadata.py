"""Tests for typed vision state metadata helpers."""

import uuid
from datetime import datetime, timedelta, timezone

from services.vision_state_metadata import (
    CURRENT_STATES_METADATA_KEY,
    UNSPECIFIED_CURRENT_STATE_TYPE,
    clear_current_state_metadata,
    current_state_id_from_metadata,
    current_state_metadata_key,
    get_current_states_metadata,
    set_current_state_metadata,
)


def test_current_state_metadata_key_uses_state_id_mapping() -> None:
    state_id = uuid.uuid4()

    result = current_state_metadata_key(
        None,
        state_id,
        {state_id: " occupation "},
    )

    assert result == "occupation"


def test_current_state_metadata_key_falls_back_to_unspecified() -> None:
    state_id = uuid.uuid4()

    assert (
        current_state_metadata_key("", state_id, {state_id: "  "})
        == UNSPECIFIED_CURRENT_STATE_TYPE
    )
    assert current_state_metadata_key(None) == UNSPECIFIED_CURRENT_STATE_TYPE


def test_current_state_id_from_metadata_parses_uuid_values() -> None:
    state_id = uuid.uuid4()

    assert (
        current_state_id_from_metadata(
            {"occupation": {"state_definition_id": state_id}},
            "occupation",
        )
        == state_id
    )
    assert (
        current_state_id_from_metadata(
            {"occupation": {"state_definition_id": str(state_id)}},
            "occupation",
        )
        == state_id
    )


def test_current_state_id_from_metadata_ignores_invalid_values() -> None:
    assert (
        current_state_id_from_metadata(
            {"occupation": {"state_definition_id": "not-a-uuid"}},
            "occupation",
        )
        is None
    )
    assert (
        current_state_id_from_metadata(
            {"occupation": {"state_definition_id": 123}},
            "occupation",
        )
        is None
    )


def test_set_current_state_metadata_preserves_existing_metadata() -> None:
    state_id = uuid.uuid4()
    observed_at = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)

    result = set_current_state_metadata(
        {"label": "patio"},
        "occupation",
        state_id,
        "occupied",
        observed_at,
        observed_at,
        0.8,
    )

    assert result["label"] == "patio"
    assert get_current_states_metadata(result)["occupation"] == {
        "state_definition_id": str(state_id),
        "state": "occupied",
        "current_state_since": observed_at.isoformat(),
        "observed_at": observed_at.isoformat(),
        "confidence": 0.8,
    }
    assert CURRENT_STATES_METADATA_KEY in result


def test_set_current_state_metadata_can_store_recovery_fields() -> None:
    state_id = uuid.uuid4()
    previous_state_id = uuid.uuid4()
    event_id = uuid.uuid4()
    observed_at = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    previous_since = observed_at - timedelta(minutes=5)

    result = set_current_state_metadata(
        {},
        "cleanliness",
        state_id,
        "clean",
        observed_at,
        observed_at,
        0.9,
        state_change_event_id=event_id,
        previous_state_id=previous_state_id,
        previous_state_name="dirty",
        previous_state_since=previous_since,
    )

    current_state = get_current_states_metadata(result)["cleanliness"]
    assert isinstance(current_state, dict)
    assert current_state["state_change_event_id"] == str(event_id)
    assert current_state["previous_state_definition_id"] == str(previous_state_id)
    assert current_state["previous_state"] == "dirty"
    assert current_state["previous_state_since"] == previous_since.isoformat()


def test_clear_current_state_metadata_removes_one_state_type() -> None:
    cleanliness_id = uuid.uuid4()
    occupation_id = uuid.uuid4()
    metadata = {
        "label": "patio",
        CURRENT_STATES_METADATA_KEY: {
            "cleanliness": {"state_definition_id": str(cleanliness_id)},
            "occupation": {"state_definition_id": str(occupation_id)},
        },
    }

    result = clear_current_state_metadata(metadata, "cleanliness")

    assert result["label"] == "patio"
    assert get_current_states_metadata(result) == {
        "occupation": {"state_definition_id": str(occupation_id)}
    }


def test_clear_current_state_metadata_removes_metadata_key_for_last_state() -> None:
    cleanliness_id = uuid.uuid4()
    metadata = {
        "label": "patio",
        CURRENT_STATES_METADATA_KEY: {
            "cleanliness": {"state_definition_id": str(cleanliness_id)},
        },
    }

    result = clear_current_state_metadata(metadata, "cleanliness")

    assert result == {"label": "patio"}
    assert get_current_states_metadata(result) == {}
