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


class VoiceConfigUpdateData(BaseModel):
    """Single voice config update data for batch operations"""

    project_id: uuid.UUID = Field(
        ..., description="ID of the project to update voice config for"
    )
    language: Optional[str] = None
    voice_id: Optional[str] = None
    first_message: Optional[str] = None
    transfer_message: Optional[str] = None
    replacements: Optional[dict] = None
    speech_rate: Optional[SpeechRate] = None
    background_sound: Optional[str] = None
    raw_config: Optional[dict] = None
    cloned: Optional[bool] = None


class BatchUpdateVoiceConfigsRequest(BaseModel):
    """Request schema for batch voice config updates"""

    account_name: str = Field(..., description="Account name that owns the projects")
    voice_config_updates: list[VoiceConfigUpdateData] = Field(
        ..., min_length=1, description="List of voice config updates to apply"
    )


class VoiceConfigUpdateResult(BaseModel):
    """Result of updating a single voice config"""

    project_id: uuid.UUID
    project_name: str
    success: bool
    voice_config_id: uuid.UUID | None = None
    error_message: str | None = None


class BatchUpdateVoiceConfigsResponse(BaseModel):
    """Response schema for batch voice config updates"""

    account_name: str
    total_requested: int
    total_updated: int
    total_failed: int
    results: list[VoiceConfigUpdateResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_requested == 0:
            return 0.0
        return (self.total_updated / self.total_requested) * 100.0
