"""Tests for voice service business logic."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.admin.voice_config import (
    CreateVoiceConfigRequest,
    UpdateVoiceConfigRequest,
)
from db.tables.voice_configs import SpeechRate
from services.voice_service import VoiceService


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def voice_service() -> VoiceService:
    """Voice service instance."""
    return VoiceService()


@pytest.fixture
def sample_create_request() -> CreateVoiceConfigRequest:
    """Sample voice config creation request."""
    return CreateVoiceConfigRequest(
        project_id=uuid.uuid4(),
        language="en",
        voice_id="test-voice",
        first_message="Hello",
        transfer_message="Transferring",
        replacements={},
        speech_rate=SpeechRate.normal,
        background_sound="office",
        raw_config={},
    )


class TestCreateVoiceConfigDuplicateValidation:
    """Test duplicate language validation in create_voice_config."""

    @pytest.mark.asyncio
    async def test_create_with_duplicate_language_raises_409(
        self,
        voice_service: VoiceService,
        sample_create_request: CreateVoiceConfigRequest,
        mock_async_session: AsyncMock,
    ) -> None:
        """Should raise 409 when creating voice config with duplicate language."""
        # Mock existing voice config with same language
        existing_config = MagicMock()
        existing_config.language = "en"
        existing_config.project_id = sample_create_request.project_id

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_configs_by_project.return_value = [existing_config]

            with pytest.raises(HTTPException) as exc_info:
                await voice_service.create_voice_config(
                    sample_create_request, mock_async_session
                )

            assert exc_info.value.status_code == 409
            assert "already exists" in exc_info.value.detail.lower()
            assert "en" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_with_different_language_succeeds(
        self,
        voice_service: VoiceService,
        sample_create_request: CreateVoiceConfigRequest,
        mock_async_session: AsyncMock,
    ) -> None:
        """Should succeed when language is different."""
        # Existing config has different language
        existing_config = MagicMock()
        existing_config.language = "es"
        existing_config.project_id = sample_create_request.project_id

        mock_created_config = MagicMock()
        mock_created_config.id = uuid.uuid4()
        mock_created_config.language = "en"
        mock_created_config.created_at = MagicMock()
        mock_created_config.updated_at = None

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_configs_by_project.return_value = [existing_config]
            mock_repo.create_voice_config.return_value = mock_created_config

            with patch("services.voice_service._implementation.build_voice_config"):
                await voice_service.create_voice_config(
                    sample_create_request, mock_async_session
                )

    @pytest.mark.asyncio
    async def test_create_first_voice_config_for_project_succeeds(
        self,
        voice_service: VoiceService,
        sample_create_request: CreateVoiceConfigRequest,
        mock_async_session: AsyncMock,
    ) -> None:
        """Should succeed when no existing voice configs for project."""
        mock_created_config = MagicMock()
        mock_created_config.id = uuid.uuid4()
        mock_created_config.language = "en"

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_configs_by_project.return_value = []
            mock_repo.create_voice_config.return_value = mock_created_config

            with patch("services.voice_service._implementation.build_voice_config"):
                await voice_service.create_voice_config(
                    sample_create_request, mock_async_session
                )


class TestUpdateVoiceConfigDuplicateValidation:
    """Test duplicate language validation in update_voice_config."""

    @pytest.mark.asyncio
    async def test_update_to_duplicate_language_raises_409(
        self, voice_service: VoiceService, mock_async_session: AsyncMock
    ) -> None:
        """Should raise 409 when updating to duplicate language."""
        voice_config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        existing_config = MagicMock()
        existing_config.id = voice_config_id
        existing_config.language = "en"
        existing_config.project_id = project_id

        other_config = MagicMock()
        other_config.id = uuid.uuid4()
        other_config.language = "es"
        other_config.project_id = project_id

        update_request = UpdateVoiceConfigRequest(language="es")

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_config_by_id.return_value = existing_config
            mock_repo.get_voice_configs_by_project.return_value = [
                existing_config,
                other_config,
            ]

            with pytest.raises(HTTPException) as exc_info:
                await voice_service.update_voice_config(
                    voice_config_id, update_request, mock_async_session
                )

            assert exc_info.value.status_code == 409
            assert "already exists" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_update_to_same_language_succeeds(
        self, voice_service: VoiceService, mock_async_session: AsyncMock
    ) -> None:
        """Should succeed when updating to same language."""
        voice_config_id = uuid.uuid4()
        project_id = uuid.uuid4()

        existing_config = MagicMock()
        existing_config.id = voice_config_id
        existing_config.language = "en"
        existing_config.project_id = project_id

        update_request = UpdateVoiceConfigRequest(language="en")

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_config_by_id.return_value = existing_config
            mock_repo.update_voice_config.return_value = existing_config

            with patch("services.voice_service._implementation.build_voice_config"):
                await voice_service.update_voice_config(
                    voice_config_id, update_request, mock_async_session
                )

    @pytest.mark.asyncio
    async def test_update_without_language_change_succeeds(
        self, voice_service: VoiceService, mock_async_session: AsyncMock
    ) -> None:
        """Should succeed when updating other fields."""
        voice_config_id = uuid.uuid4()

        existing_config = MagicMock()
        existing_config.id = voice_config_id
        existing_config.language = "en"

        update_request = UpdateVoiceConfigRequest(first_message="New message")

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_config_by_id.return_value = existing_config
            mock_repo.update_voice_config.return_value = existing_config

            with patch("services.voice_service._implementation.build_voice_config"):
                await voice_service.update_voice_config(
                    voice_config_id, update_request, mock_async_session
                )

    @pytest.mark.asyncio
    async def test_update_nonexistent_config_raises_404(
        self, voice_service: VoiceService, mock_async_session: AsyncMock
    ) -> None:
        """Should raise 404 when updating non-existent config."""
        voice_config_id = uuid.uuid4()
        update_request = UpdateVoiceConfigRequest(language="en")

        with patch(
            "services.voice_service._implementation.VoiceConfigRepositoryAsync"
        ) as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_voice_config_by_id.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await voice_service.update_voice_config(
                    voice_config_id, update_request, mock_async_session
                )

            assert exc_info.value.status_code == 404
