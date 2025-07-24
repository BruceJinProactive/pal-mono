import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.tables.prompts import Prompt, PromptDetails
from db.tables.types import Channel
from utils.log import logger


class PromptRepository:
    def __init__(self, session: Session, auto_commit: bool = True):
        self.session = session
        self.auto_commit = auto_commit

    def _convert_channels(self, channels: list) -> list:
        """Convert string channel values to Channel enum members."""
        converted_channels = []
        for channel_str in channels:
            if isinstance(channel_str, str):
                matching_enum = None
                for channel_enum in Channel:
                    if channel_enum.value == channel_str.lower():
                        matching_enum = channel_enum
                        break
                if matching_enum:
                    converted_channels.append(matching_enum)
                else:
                    logger.warning(f"Unknown channel value: {channel_str}")
            else:
                converted_channels.append(channel_str)
        return converted_channels

    def create_prompt(self, **kwargs) -> Prompt:
        try:
            prompt = Prompt(id=uuid.uuid4())
            for key, value in kwargs.items():
                if value is not None and hasattr(prompt, key):
                    if key == "channel" and isinstance(value, list):
                        setattr(prompt, key, self._convert_channels(value))
                    else:
                        setattr(prompt, key, value)

            self.session.add(prompt)
            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(prompt)
            return prompt
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating prompt: {e}")
            raise

    def create_prompt_details(self, **kwargs) -> PromptDetails:
        try:
            prompt_details = PromptDetails(id=uuid.uuid4())
            for key, value in kwargs.items():
                if value is not None and hasattr(prompt_details, key):
                    setattr(prompt_details, key, value)

            self.session.add(prompt_details)
            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(prompt_details)
            return prompt_details
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error creating prompt details: {e}")
            raise

    def get_latest_prompt_details(self, prompt_id: uuid.UUID) -> PromptDetails | None:
        return (
            self.session.query(PromptDetails)
            .filter(PromptDetails.prompt_id == prompt_id)
            .order_by(PromptDetails.version_number.desc())
            .first()
        )

    def get_prompts(
        self,
        resource_type: str | None = None,
        resource_id: uuid.UUID | None = None,
        search: str | None = None,
        channels: list[str] | None = None,
    ) -> list[Prompt]:
        query = self.session.query(Prompt).filter(~Prompt.deleted)

        if resource_type:
            query = query.filter(Prompt.resource_type == resource_type)
        if resource_id:
            query = query.filter(Prompt.resource_id == resource_id)
        if search:
            query = query.filter(Prompt.name.ilike(f"%{search}%"))
        if channels:
            channel_enums = []
            for channel_str in channels:
                for channel_enum in Channel:
                    if channel_enum.value == channel_str.lower():
                        channel_enums.append(channel_enum)
                        break
            if channel_enums:
                query = query.filter(
                    (Prompt.channel.is_(None))
                    | (Prompt.channel == [])
                    | (Prompt.channel.overlap(channel_enums))
                )

        return query.order_by(Prompt.created_at.desc()).all()

    def get_prompt_by_id(self, prompt_id: uuid.UUID) -> Prompt | None:
        return (
            self.session.query(Prompt)
            .filter(Prompt.id == prompt_id, ~Prompt.deleted)
            .first()
        )

    def update_prompt(self, prompt_id: uuid.UUID, **kwargs) -> Prompt | None:
        try:
            prompt = self.get_prompt_by_id(prompt_id)
            if not prompt:
                return None

            for key, value in kwargs.items():
                if value is not None and hasattr(prompt, key):
                    if key == "channel" and isinstance(value, list):
                        setattr(prompt, key, self._convert_channels(value))
                    else:
                        setattr(prompt, key, value)

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            self.session.refresh(prompt)
            return prompt
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error updating prompt: {e}")
            raise

    def get_next_version_number(self, prompt_id: uuid.UUID) -> int:
        latest_details = self.get_latest_prompt_details(prompt_id)
        return (latest_details.version_number + 1) if latest_details else 1

    def get_all_prompt_versions(self, prompt_id: uuid.UUID) -> list[PromptDetails]:
        return (
            self.session.query(PromptDetails)
            .filter(PromptDetails.prompt_id == prompt_id)
            .order_by(PromptDetails.version_number.desc())
            .all()
        )

    def delete_prompt(self, prompt_id: uuid.UUID) -> bool:
        try:
            prompt = self.get_prompt_by_id(prompt_id)
            if not prompt:
                return False

            prompt.deleted = True

            if self.auto_commit:
                self.session.commit()
            else:
                self.session.flush()

            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting prompt: {e}")
            raise
