from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class VoiceConfigData:
    """Immutable snapshot of a voice config.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    project_id: uuid.UUID
    language: str
    voice_id: str
    first_message: str
    transfer_message: str
    speech_rate: str
    background_sound: str
    voice_model: str
    replacements: dict[str, Any] = field(default_factory=dict)
    raw_config: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID | None = None
    pronunciation_dict_id: str | None = None
    cloned_voice_id: str | None = None
    transcriber: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "replacements", dict(self.replacements))
        object.__setattr__(self, "raw_config", dict(self.raw_config))
        object.__setattr__(
            self,
            "transcriber",
            None if self.transcriber is None else dict(self.transcriber),
        )
