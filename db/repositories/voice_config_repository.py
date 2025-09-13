import uuid
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import VoiceConfig


class VoiceConfigRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_voice_config(
        self,
        project_id: uuid.UUID,
        language: str,
        voice_id: str,
        first_message: str,
        transfer_message: str,
        replacements: Optional[Dict] = None,
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
        )
        self.session.add(db_voice_config)
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
