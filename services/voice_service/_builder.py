"""Voice config response builders for API schemas."""

import db
from api.schemas.admin.voice_config import VoiceConfig


def build_voice_config(voice_config: db.VoiceConfig) -> VoiceConfig:
    """Build VoiceConfig from database VoiceConfig."""
    return VoiceConfig(
        id=voice_config.id,
        project_id=voice_config.project_id,
        language=voice_config.language,
        voice_id=voice_config.voice_id,
        replacements=voice_config.replacements,
        first_message=voice_config.first_message,
        transfer_message=voice_config.transfer_message,
        speech_rate=voice_config.speech_rate,
        background_sound=voice_config.background_sound,
        raw_config=voice_config.raw_config,
        pronunciation_dict_id=voice_config.pronunciation_dict_id,
        cloned_voice_id=voice_config.cloned_voice_id,
        voice_model=voice_config.voice_model,
        transcriber=voice_config.transcriber,
        created_at=int(voice_config.created_at.timestamp()),
        updated_at=int(
            voice_config.updated_at.timestamp() if voice_config.updated_at else 0
        ),
    )
