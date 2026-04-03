import uuid
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.tables import VoiceConfig
from db.tables.types import SpeechRate


class VoiceConfigRepositoryAsync:
    def __init__(self, session: AsyncSession, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    async def create_voice_config(
        self,
        project_id: uuid.UUID,
        language: str,
        voice_id: str,
        first_message: str,
        transfer_message: str,
        replacements: Optional[Dict] = None,
        speech_rate: Optional[str] = None,
        background_sound: Optional[str] = None,
        raw_config: Optional[Dict] = None,
        cloned_voice_id: Optional[str] = None,
        voice_model: Optional[str] = None,
        transcriber: Optional[Dict] = None,
        pronunciation_dict_id: Optional[str] = None,
    ) -> VoiceConfig:
        """
        Create a new voice config asynchronously.

        Args:
            project_id (uuid.UUID): The project ID
            language (str): The language code
            voice_id (str): The voice ID
            first_message (str): The first message
            transfer_message (str): The transfer message
            replacements (Optional[Dict]): Replacements dictionary, defaults to empty dict
            speech_rate (Optional[str]): The speech rate
            background_sound (Optional[str]): The background sound
            raw_config (Optional[Dict]): Raw configuration dictionary
            cloned_voice_id (Optional[str]): The cloned voice ID
            voice_model (Optional[str]): The voice model (sonic-2 or sonic-3)
            transcriber (Optional[Dict]): The transcriber configuration
            pronunciation_dict_id (Optional[str]): Cartesia pronunciation dictionary ID

        Returns:
            VoiceConfig: The created voice config
        """
        db_voice_config = VoiceConfig(
            project_id=project_id,
            language=language,
            voice_id=voice_id,
            first_message=first_message,
            transfer_message=transfer_message,
            replacements=replacements or {},
            speech_rate=SpeechRate(speech_rate) if speech_rate else SpeechRate.normal,
            background_sound=background_sound,
            raw_config=raw_config or {},
            cloned_voice_id=cloned_voice_id,
            voice_model=voice_model or "sonic-2",
            transcriber=transcriber,
            pronunciation_dict_id=pronunciation_dict_id,
        )
        self.session.add(db_voice_config)

        if self.auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()

        await self.session.refresh(db_voice_config)
        return db_voice_config

    async def get_voice_configs_by_project(
        self, project_id: uuid.UUID
    ) -> List[VoiceConfig]:
        """
        Get all voice configs for a project asynchronously.

        Args:
            project_id (uuid.UUID): The project ID

        Returns:
            List[VoiceConfig]: List of voice configs for the project
        """
        query = select(VoiceConfig).filter(VoiceConfig.project_id == project_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_voice_config_by_id(
        self, voice_config_id: uuid.UUID
    ) -> Optional[VoiceConfig]:
        """
        Get a voice config by ID asynchronously.

        Args:
            voice_config_id (uuid.UUID): The voice config ID

        Returns:
            Optional[VoiceConfig]: The voice config if found, None otherwise
        """
        query = select(VoiceConfig).filter(VoiceConfig.id == voice_config_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def update_voice_config(
        self, voice_config_id: uuid.UUID, **kwargs
    ) -> Optional[VoiceConfig]:
        """
        Update a voice config asynchronously.

        Args:
            voice_config_id (uuid.UUID): The voice config ID
            **kwargs: Fields to update (language, voice_id, first_message,
                     transfer_message, replacements, speech_rate, background_sound, raw_config)

        Returns:
            Optional[VoiceConfig]: The updated voice config if found, None otherwise
        """
        # Get the existing voice config
        voice_config = await self.get_voice_config_by_id(voice_config_id)
        if not voice_config:
            return None

        # Update only provided fields
        for key, value in kwargs.items():
            if value is not None and hasattr(voice_config, key):
                if key == "speech_rate":
                    setattr(voice_config, key, SpeechRate(value))
                else:
                    setattr(voice_config, key, value)

        if self.auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()

        await self.session.refresh(voice_config)
        return voice_config

    async def delete_voice_config(self, voice_config_id: uuid.UUID) -> bool:
        """
        Delete a voice config asynchronously.

        Args:
            voice_config_id (uuid.UUID): The voice config ID

        Returns:
            bool: True if deleted, False if not found
        """
        voice_config = await self.get_voice_config_by_id(voice_config_id)
        if not voice_config:
            return False

        await self.session.delete(voice_config)

        if self.auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()

        return True

    async def delete_voice_configs_by_project(self, project_id: uuid.UUID) -> int:
        """
        Delete all voice configs for a project asynchronously.

        Args:
            project_id (uuid.UUID): The project ID

        Returns:
            int: Number of voice configs deleted
        """
        voice_configs = await self.get_voice_configs_by_project(project_id)
        deleted_count = 0

        for voice_config in voice_configs:
            await self.session.delete(voice_config)
            deleted_count += 1

        if self.auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()

        return deleted_count


class VoiceConfigRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def create_voice_config(
        self,
        project_id: uuid.UUID,
        language: str,
        voice_id: str,
        first_message: str,
        transfer_message: str,
        replacements: Optional[Dict] = None,
        speech_rate: Optional[str] = None,
        background_sound: Optional[str] = None,
        raw_config: Optional[Dict] = None,
        cloned_voice_id: Optional[str] = None,
        voice_model: Optional[str] = None,
        transcriber: Optional[Dict] = None,
        pronunciation_dict_id: Optional[str] = None,
    ) -> VoiceConfig:
        """
        Create a new voice config synchronously.

        Args:
            project_id (uuid.UUID): The project ID
            language (str): The language code
            voice_id (str): The voice ID
            first_message (str): The first message
            transfer_message (str): The transfer message
            replacements (Optional[Dict]): Replacements dictionary, defaults to empty dict
            speech_rate (Optional[str]): The speech rate
            background_sound (Optional[str]): The background sound
            raw_config (Optional[Dict]): Raw configuration dictionary
            cloned_voice_id (Optional[str]): The cloned voice ID
            voice_model (Optional[str]): The voice model (sonic-2 or sonic-3)
            transcriber (Optional[Dict]): The transcriber configuration
            pronunciation_dict_id (Optional[str]): Cartesia pronunciation dictionary ID

        Returns:
            VoiceConfig: The created voice config
        """
        db_voice_config = VoiceConfig(
            project_id=project_id,
            language=language,
            voice_id=voice_id,
            first_message=first_message,
            transfer_message=transfer_message,
            replacements=replacements or {},
            speech_rate=SpeechRate(speech_rate) if speech_rate else SpeechRate.normal,
            background_sound=background_sound,
            raw_config=raw_config or {},
            cloned_voice_id=cloned_voice_id,
            voice_model=voice_model or "sonic-2",
            transcriber=transcriber,
            pronunciation_dict_id=pronunciation_dict_id,
        )
        self.session.add(db_voice_config)

        if self.auto_commit:
            self.session.commit()
        else:
            self.session.flush()

        self.session.refresh(db_voice_config)
        return db_voice_config

    def get_voice_configs_by_project(self, project_id: uuid.UUID) -> List[VoiceConfig]:
        """
        Get all voice configs for a project synchronously.

        Args:
            project_id (uuid.UUID): The project ID

        Returns:
            List[VoiceConfig]: List of voice configs for the project
        """
        query = select(VoiceConfig).filter(VoiceConfig.project_id == project_id)
        result = self.session.execute(query)
        return list(result.scalars().all())

    def delete_voice_configs_by_project(self, project_id: uuid.UUID) -> int:
        """
        Delete all voice configs for a project synchronously.

        Args:
            project_id (uuid.UUID): The project ID

        Returns:
            int: Number of voice configs deleted
        """
        voice_configs = self.get_voice_configs_by_project(project_id)
        deleted_count = 0

        for voice_config in voice_configs:
            self.session.delete(voice_config)
            deleted_count += 1

        if self.auto_commit:
            self.session.commit()
        else:
            self.session.flush()

        return deleted_count
