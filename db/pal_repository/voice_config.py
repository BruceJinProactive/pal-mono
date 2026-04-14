from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.voice_config import VoiceConfigData
from db.tables.types import SpeechRate
from db.tables.voice_configs import VoiceConfig
from utils.log import logger


def _to_data(row: VoiceConfig) -> VoiceConfigData:
    """Convert an ORM VoiceConfig to a VoiceConfigData."""
    return VoiceConfigData(
        id=row.id,
        project_id=row.project_id,
        language=row.language,
        voice_id=row.voice_id,
        replacements=dict(row.replacements) if row.replacements else {},
        first_message=row.first_message,
        transfer_message=row.transfer_message,
        speech_rate=row.speech_rate.value if row.speech_rate else "",
        background_sound=row.background_sound,
        raw_config=dict(row.raw_config) if row.raw_config else {},
        pronunciation_dict_id=row.pronunciation_dict_id,
        cloned_voice_id=row.cloned_voice_id,
        voice_model=row.voice_model,
        transcriber=dict(row.transcriber) if row.transcriber is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VoiceConfigRepository:
    """Async-only repository for VoiceConfig records.

    All methods return ``VoiceConfigData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, config_id: uuid.UUID) -> VoiceConfigData | None:
        """Retrieve a single voice config by its primary key."""
        try:
            result = await self.session.execute(
                select(VoiceConfig).filter(VoiceConfig.id == config_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving voice config by ID")
            raise

    async def list_by_project_id(self, project_id: uuid.UUID) -> list[VoiceConfigData]:
        """List all voice configs for a given project."""
        try:
            result = await self.session.execute(
                select(VoiceConfig)
                .filter(VoiceConfig.project_id == project_id)
                .order_by(VoiceConfig.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing voice configs by project ID")
            raise

    async def get_by_project_and_language(
        self, project_id: uuid.UUID, language: str
    ) -> VoiceConfigData | None:
        """Retrieve a voice config for a specific project and language."""
        try:
            result = await self.session.execute(
                select(VoiceConfig).filter(
                    VoiceConfig.project_id == project_id,
                    VoiceConfig.language == language,
                )
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving voice config by project and language")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: VoiceConfigData) -> None:
        """Create a new voice config.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = VoiceConfig(
                id=record.id,
                project_id=record.project_id,
                language=record.language,
                voice_id=record.voice_id,
                replacements=dict(record.replacements),
                first_message=record.first_message,
                transfer_message=record.transfer_message,
                speech_rate=SpeechRate(record.speech_rate),
                background_sound=record.background_sound,
                raw_config=dict(record.raw_config),
                pronunciation_dict_id=record.pronunciation_dict_id,
                cloned_voice_id=record.cloned_voice_id,
                voice_model=record.voice_model,
                transcriber=(
                    dict(record.transcriber) if record.transcriber is not None else None
                ),
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating voice config: {e}")
            raise

    async def delete(self, config_id: uuid.UUID) -> VoiceConfigData | None:
        """Delete a voice config by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(VoiceConfig).filter(VoiceConfig.id == config_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting voice config: {e}")
            raise
