"""Eval API request schemas."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VoiceOverridesRequest(BaseModel):
    """Run-level voice parameter overrides.

    When provided on ``RunEvalRequest``, these override persona/speed/noise
    settings for ALL scenarios in the run — useful for stress-testing agent
    robustness without editing YAML files.

    Only non-None fields take effect; omitted fields fall through to
    scenario-level or persona-registry defaults.
    """

    persona: str | None = Field(
        default=None,
        description="Override persona name for all scenarios",
    )
    speed: float | None = Field(
        default=None,
        gt=0.0,
        le=3.0,
        description="Override speech speed multiplier (0.5=slow, 1.0=normal, 2.0=fast)",
    )
    background_noise: bool | None = Field(
        default=None,
        description="Force background noise on (True) or off (False) for all scenarios",
    )
    noise_level_db: float | None = Field(
        default=None,
        ge=-60.0,
        le=0.0,
        description="Noise level in dB relative to speech (-20=subtle, -6=loud)",
    )
    noise_type: Literal["street", "car", "home"] | None = Field(
        default=None,
        description="Type of background noise environment",
    )


class RunEvalRequest(BaseModel):
    """Request to trigger an evaluation run for a project.

    The ``project_id`` is looked up in ``project_map.json`` to find the
    matching scenario directory name for loading test scenarios.
    """

    project_id: uuid.UUID = Field(
        ...,
        description="Project UUID to evaluate",
    )
    account_id: uuid.UUID = Field(..., description="Account that owns the project")
    channel_identifier: str = Field(
        ...,
        description="Channel identifier for routing messages (e.g. 'api:pokeworks-san_jose')",
    )

    @field_validator("channel_identifier")
    @classmethod
    def validate_channel_identifier(cls, v: str) -> str:
        """Ensure format is 'channel:identifier' with non-empty parts."""
        if ":" not in v:
            raise ValueError(
                "channel_identifier must be in 'channel:identifier' format "
                "(e.g. 'api:pokeworks-san_jose')"
            )
        channel, identifier = v.split(":", 1)
        if not channel or not identifier:
            raise ValueError(
                "channel_identifier must have non-empty channel and identifier "
                "(e.g. 'api:pokeworks-san_jose')"
            )
        return v

    driver: Literal["http", "direct", "voice"] = Field(
        default="http",
        description="Driver mode: http (real system), direct (in-process, not yet implemented), or voice (LiveKit room injection)",
    )

    triggered_by: str = Field(
        default="api",
        max_length=20,
        description="Who triggered the run",
    )

    max_concurrency: int | None = Field(
        default=None,
        ge=1,
        le=64,
        description=(
            "Max scenarios to run in parallel. None uses the service default "
            "(currently 4). Applies to all driver modes including voice; pick "
            "a value appropriate to your LiveKit worker pool and "
            "TTS/STT rate limits."
        ),
    )

    voice_overrides: VoiceOverridesRequest | None = Field(
        default=None,
        description=(
            "Run-level voice parameter overrides. When set, these take highest "
            "priority over scenario-level persona settings. Only meaningful "
            "when driver='voice'."
        ),
    )


class ComputeSnapshotDiffRequest(BaseModel):
    """Request body for computing a diff between two agent config snapshots."""

    from_fingerprint: str = Field(
        ..., description="Fingerprint of the baseline (older) snapshot"
    )
    to_fingerprint: str = Field(
        ..., description="Fingerprint of the target (newer) snapshot"
    )
