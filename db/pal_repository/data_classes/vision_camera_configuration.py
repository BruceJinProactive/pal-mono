from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class VisionCameraConfigurationData:
    id: uuid.UUID
    signal_source_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    llm_prompt: str
    llm_provider: str
    llm_model: str
    processing_interval_seconds: int
    reference_images: List[object]
    enabled: bool
    created_at: datetime
    structured_observations_enabled: bool = False
    updated_at: datetime | None = None
