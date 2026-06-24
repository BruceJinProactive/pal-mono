from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone

CURRENT_STATES_METADATA_KEY = "current_states"
LEGACY_CURRENT_STATE_TYPE = "state"
UNSPECIFIED_CURRENT_STATE_TYPE = "__unspecified__"


def current_state_metadata_key(
    definition_type: str | None,
    state_id: uuid.UUID | None = None,
    state_id_to_definition_type: dict[uuid.UUID, str | None] | None = None,
) -> str:
    if definition_type and definition_type.strip():
        return definition_type.strip()

    if state_id is not None and state_id_to_definition_type is not None:
        mapped_definition_type = state_id_to_definition_type.get(state_id)
        if mapped_definition_type and mapped_definition_type.strip():
            return mapped_definition_type.strip()

    return UNSPECIFIED_CURRENT_STATE_TYPE


def get_current_states_metadata(
    entity_metadata: dict[str, object],
) -> dict[str, object]:
    current_states = entity_metadata.get(CURRENT_STATES_METADATA_KEY)
    if not isinstance(current_states, Mapping):
        return {}
    return {str(key): value for key, value in current_states.items()}


def current_state_id_from_metadata(
    current_states: dict[str, object],
    definition_type: str,
) -> uuid.UUID | None:
    current_state = current_states.get(definition_type)
    if not isinstance(current_state, Mapping):
        return None

    raw_state_id = current_state.get("state_definition_id")
    if isinstance(raw_state_id, uuid.UUID):
        return raw_state_id
    if isinstance(raw_state_id, str):
        try:
            return uuid.UUID(raw_state_id)
        except ValueError:
            return None
    return None


def current_state_observed_at_from_metadata(
    current_states: dict[str, object],
    definition_type: str,
) -> datetime | None:
    current_state = current_states.get(definition_type)
    if not isinstance(current_state, Mapping):
        return None

    raw_observed_at = current_state.get("observed_at")
    if isinstance(raw_observed_at, datetime):
        return _as_utc(raw_observed_at)
    if isinstance(raw_observed_at, str):
        try:
            return _as_utc(datetime.fromisoformat(raw_observed_at))
        except ValueError:
            return None
    return None


def set_current_state_metadata(
    entity_metadata: dict[str, object],
    definition_type: str,
    state_id: uuid.UUID,
    state_name: str,
    current_state_since: datetime,
    observed_at: datetime,
    confidence: float | None,
    state_change_event_id: uuid.UUID | None = None,
    previous_state_id: uuid.UUID | None = None,
    previous_state_name: str | None = None,
    previous_state_since: datetime | None = None,
) -> dict[str, object]:
    updated_metadata = dict(entity_metadata)
    current_states = get_current_states_metadata(updated_metadata)
    current_state: dict[str, object] = {
        "state_definition_id": str(state_id),
        "state": state_name,
        "current_state_since": current_state_since.isoformat(),
        "observed_at": observed_at.isoformat(),
    }
    if confidence is not None:
        current_state["confidence"] = confidence
    if state_change_event_id is not None:
        current_state["state_change_event_id"] = str(state_change_event_id)
    if previous_state_id is not None:
        current_state["previous_state_definition_id"] = str(previous_state_id)
    if previous_state_name is not None:
        current_state["previous_state"] = previous_state_name
    if previous_state_since is not None:
        current_state["previous_state_since"] = previous_state_since.isoformat()

    current_states[definition_type] = current_state
    updated_metadata[CURRENT_STATES_METADATA_KEY] = current_states
    return updated_metadata


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def clear_current_state_metadata(
    entity_metadata: dict[str, object],
    definition_type: str,
) -> dict[str, object]:
    updated_metadata = dict(entity_metadata)
    current_states = get_current_states_metadata(updated_metadata)
    current_states.pop(definition_type, None)

    if current_states:
        updated_metadata[CURRENT_STATES_METADATA_KEY] = current_states
    else:
        updated_metadata.pop(CURRENT_STATES_METADATA_KEY, None)

    return updated_metadata
