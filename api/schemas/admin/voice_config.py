import uuid
from typing import Optional

from pydantic import BaseModel, Field

from db.tables.voice_configs import SpeechRate


class VoiceConfig(BaseModel):
    """Voice Config Model"""

    id: uuid.UUID
    project_id: uuid.UUID
    language: str
    voice_id: str
    replacements: dict
    first_message: str
    transfer_message: str
    speech_rate: SpeechRate
    background_sound: str
    raw_config: dict
    cloned_voice_id: Optional[str] = None
    created_at: int  # timestamp in seconds and UTC tz
    updated_at: int  # timestamp in seconds and UTC tz


class CreateVoiceConfigRequest(BaseModel):
    """Create Voice Config Request"""

    project_id: uuid.UUID = Field(...)
    language: str = Field(...)
    voice_id: str = Field(...)
    first_message: str = Field(...)
    transfer_message: str = Field(...)
    replacements: Optional[dict] = Field(default_factory=dict)
    speech_rate: Optional[SpeechRate] = SpeechRate.normal
    background_sound: Optional[str] = "office"
    raw_config: Optional[dict] = Field(default_factory=dict)
    cloned: Optional[bool] = False


class UpdateVoiceConfigRequest(BaseModel):
    """Update Voice Config Request"""

    language: Optional[str] = None
    voice_id: Optional[str] = None
    first_message: Optional[str] = None
    transfer_message: Optional[str] = None
    replacements: Optional[dict] = None
    speech_rate: Optional[SpeechRate] = None
    background_sound: Optional[str] = None
    raw_config: Optional[dict] = None
    cloned: Optional[bool] = None


class ListVoiceConfigsResponse(BaseModel):
    """List Voice Configs Response"""

    voice_configs: list[VoiceConfig]
    total_count: int
