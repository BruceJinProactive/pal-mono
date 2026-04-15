"""Tests for monitoring config restructure — service layer.

Validates that upload_reference_images stores flag per image,
and that update_config handles context, pass_criteria, fail_criteria.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.schemas.operations.monitoring import UpdateMonitoringConfigRequest


class TestUploadReferenceImagesFlags:
    """Test that upload_reference_images stores pass/fail flag per image."""

    @pytest.mark.asyncio
    async def test_stores_flag_on_each_image(self, mocker) -> None:
        """Each uploaded image should include its pass/fail flag in the returned dict."""
        from services.monitoring_service._implementation import upload_reference_images

        mock_image1 = MagicMock()
        mock_image1.filename = "clean.jpg"
        mock_image1.read = AsyncMock(return_value=b"fake-image-1")
        mock_image2 = MagicMock()
        mock_image2.filename = "dirty.jpg"
        mock_image2.read = AsyncMock(return_value=b"fake-image-2")

        mocker.patch(
            "services.monitoring_service._implementation.write_asset",
            return_value=MagicMock(url="s3://test/image.jpg"),
        )
        mocker.patch(
            "services.monitoring_service._implementation.asyncio.to_thread",
            side_effect=lambda fn, *a, **kw: fn(*a, **kw),
        )

        result = await upload_reference_images(
            images=[mock_image1, mock_image2],
            descriptions=["Clean kitchen", "Dirty counter"],
            project_id=uuid.uuid4(),
            config_id=uuid.uuid4(),
            flags=["pass", "fail"],
        )

        assert len(result) == 2
        assert result[0]["flag"] == "pass"
        assert result[1]["flag"] == "fail"

    @pytest.mark.asyncio
    async def test_defaults_flag_to_pass_when_no_flags(self, mocker) -> None:
        """When flags parameter is empty/None, should default to 'pass'."""
        from services.monitoring_service._implementation import upload_reference_images

        mock_image = MagicMock()
        mock_image.filename = "test.jpg"
        mock_image.read = AsyncMock(return_value=b"fake")

        mocker.patch(
            "services.monitoring_service._implementation.write_asset",
            return_value=MagicMock(url="s3://test/image.jpg"),
        )
        mocker.patch(
            "services.monitoring_service._implementation.asyncio.to_thread",
            side_effect=lambda fn, *a, **kw: fn(*a, **kw),
        )

        result = await upload_reference_images(
            images=[mock_image],
            descriptions=["Test"],
            project_id=uuid.uuid4(),
            config_id=uuid.uuid4(),
        )

        assert result[0]["flag"] == "pass"


class TestUpdateConfigContextField:
    """Test that update_config handles context field in rules JSONB."""

    @pytest.mark.asyncio
    async def test_updates_context_in_rules(self, mocker) -> None:
        """Should set 'context' in rules when context is provided."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project_repo = mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        )
        mock_project_repo.return_value.get_project = AsyncMock(
            return_value=mock_project
        )

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Existing Config"
        mock_config.rules = {"prompt": "old prompt", "reference_images": []}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            context="New scene context",
            name=None,
            description=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        updated_rules = update_call.kwargs.get("rules") or update_call[1].get("rules")
        assert updated_rules["context"] == "New scene context"

    @pytest.mark.asyncio
    async def test_prompt_also_sets_context_for_backward_compat(self, mocker) -> None:
        """When only prompt is updated, context should also be set for compat."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project_repo = mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        )
        mock_project_repo.return_value.get_project = AsyncMock(
            return_value=mock_project
        )

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Existing Config"
        mock_config.rules = {"prompt": "old", "reference_images": []}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        # Only prompt provided (legacy client)
        request = UpdateMonitoringConfigRequest(
            prompt="Updated prompt text",
            name=None,
            description=None,
            context=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        updated_rules = update_call.kwargs.get("rules") or update_call[1].get("rules")
        assert updated_rules["prompt"] == "Updated prompt text"
        assert updated_rules["context"] == "Updated prompt text"


class TestUpdateConfigCriteria:
    """Test that update_config handles pass_criteria and fail_criteria."""

    @pytest.mark.asyncio
    async def test_updates_pass_criteria_in_rules(self, mocker) -> None:
        """Should update 'pass_criteria' in rules JSONB."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project_repo = mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        )
        mock_project_repo.return_value.get_project = AsyncMock(
            return_value=mock_project
        )

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.rules = {
            "context": "test",
            "pass_criteria": [],
            "fail_criteria": [],
        }

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            pass_criteria=["Surfaces clean", "Equipment stored"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        updated_rules = update_call.kwargs.get("rules") or update_call[1].get("rules")
        assert updated_rules["pass_criteria"] == ["Surfaces clean", "Equipment stored"]

    @pytest.mark.asyncio
    async def test_updates_fail_criteria_in_rules(self, mocker) -> None:
        """Should update 'fail_criteria' in rules JSONB."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project_repo = mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        )
        mock_project_repo.return_value.get_project = AsyncMock(
            return_value=mock_project
        )

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.rules = {
            "context": "test",
            "pass_criteria": [],
            "fail_criteria": [],
        }

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            fail_criteria=["Debris visible", "Spills uncleaned"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        updated_rules = update_call.kwargs.get("rules") or update_call[1].get("rules")
        assert updated_rules["fail_criteria"] == ["Debris visible", "Spills uncleaned"]


class TestUpdateConfigReferenceImageMetadata:
    """Test updating existing reference image metadata in update_config."""

    @pytest.mark.asyncio
    async def test_updates_existing_image_flag_and_description(self, mocker) -> None:
        """Should persist both flag and description updates for existing images."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        image_id = str(uuid.uuid4())
        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.rules = {
            "context": "test",
            "reference_images": [
                {
                    "id": image_id,
                    "url": "s3://test/img.jpg",
                    "description": "before",
                    "flag": "pass",
                }
            ],
        }

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
            update_image_metadata={image_id: {"description": "after", "flag": "fail"}},
        )

        update_call = mock_config_repo.return_value.update.call_args
        updated_rules = update_call.kwargs.get("rules") or update_call[1].get("rules")
        assert updated_rules["reference_images"][0]["description"] == "after"
        assert updated_rules["reference_images"][0]["flag"] == "fail"


class TestUploadReferenceImagesFlagValidation:
    """Test that upload_reference_images validates flag inputs."""

    @pytest.mark.asyncio
    async def test_flag_count_mismatch_raises_400(self) -> None:
        """Should raise 400 when flag count does not match image count."""
        from fastapi import HTTPException

        from services.monitoring_service._implementation import upload_reference_images

        mock_image1 = MagicMock()
        mock_image1.filename = "img1.jpg"
        mock_image2 = MagicMock()
        mock_image2.filename = "img2.jpg"

        with pytest.raises(HTTPException) as exc_info:
            await upload_reference_images(
                images=[mock_image1, mock_image2],
                descriptions=["Desc 1", "Desc 2"],
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                flags=["pass"],  # 1 flag, 2 images
            )
        assert exc_info.value.status_code == 400
        assert "flags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_flag_value_raises_400(self) -> None:
        """Should raise 400 when flags contain values other than 'pass' or 'fail'."""
        from fastapi import HTTPException

        from services.monitoring_service._implementation import upload_reference_images

        mock_image = MagicMock()
        mock_image.filename = "img.jpg"

        with pytest.raises(HTTPException) as exc_info:
            await upload_reference_images(
                images=[mock_image],
                descriptions=["Desc"],
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                flags=["invalid"],
            )
        assert exc_info.value.status_code == 400
        assert "invalid" in str(exc_info.value.detail).lower()


class TestCreateConfigWithTags:
    """Test that create_config stores tags on the monitoring config."""

    @pytest.mark.asyncio
    async def test_create_with_tags(self, mocker) -> None:
        """Tags provided at creation should be stored on the config."""
        from services.monitoring_service._implementation import create_config

        session = AsyncMock()
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_source = MagicMock()
        mock_source.project_id = project_id
        mocker.patch(
            "services.monitoring_service._implementation.SignalSourceRepositoryAsync"
        ).return_value.get_by_id = AsyncMock(return_value=mock_source)

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        created = MagicMock()
        created.id = uuid.uuid4()
        mock_config_repo.return_value.create = AsyncMock(return_value=created)

        from api.schemas.operations.monitoring import (
            CreateMonitoringConfigRequest,
            MonitoringRules,
        )

        request = CreateMonitoringConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="Kitchen Check",
            description=None,
            rules=MonitoringRules(
                context="Kitchen area",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
            ),
            model=None,
            enabled=True,
            tags=["Food consistency", "Cleanliness"],
        )

        await create_config(session=session, project_id=project_id, request=request)

        create_call = mock_config_repo.return_value.create.call_args
        config_obj = create_call[0][0]
        assert config_obj.tags == ["Food consistency", "Cleanliness"]

    @pytest.mark.asyncio
    async def test_create_with_empty_tags(self, mocker) -> None:
        """Empty tags list should be stored as empty list."""
        from services.monitoring_service._implementation import create_config

        session = AsyncMock()
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_source = MagicMock()
        mock_source.project_id = project_id
        mocker.patch(
            "services.monitoring_service._implementation.SignalSourceRepositoryAsync"
        ).return_value.get_by_id = AsyncMock(return_value=mock_source)

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        created = MagicMock()
        created.id = uuid.uuid4()
        mock_config_repo.return_value.create = AsyncMock(return_value=created)

        from api.schemas.operations.monitoring import (
            CreateMonitoringConfigRequest,
            MonitoringRules,
        )

        request = CreateMonitoringConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="No Tags Config",
            description=None,
            rules=MonitoringRules(
                context="Test",
                prompt=None,
                structured_output=None,
                monitoring_time_window=None,
            ),
            model=None,
            enabled=True,
            tags=[],
        )

        await create_config(session=session, project_id=project_id, request=request)

        create_call = mock_config_repo.return_value.create.call_args
        config_obj = create_call[0][0]
        assert config_obj.tags == []


class TestUpdateConfigTags:
    """Test that update_config handles tags correctly."""

    @pytest.mark.asyncio
    async def test_add_tags_to_config_with_no_tags(self, mocker) -> None:
        """Adding tags to a config that has empty tags list."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.tags = []
        mock_config.rules = {"context": "test"}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            tags=["Food consistency", "Cleanliness"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        assert update_call.kwargs.get("tags") == ["Food consistency", "Cleanliness"]

    @pytest.mark.asyncio
    async def test_add_tags_to_config_with_existing_tags(self, mocker) -> None:
        """Replacing tags on a config that already has tags (full list replacement)."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.tags = ["Old tag"]
        mock_config.rules = {"context": "test"}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        # Replace entire list: old tag + new tags
        request = UpdateMonitoringConfigRequest(
            tags=["Old tag", "New tag 1", "New tag 2"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        assert update_call.kwargs.get("tags") == ["Old tag", "New tag 1", "New tag 2"]

    @pytest.mark.asyncio
    async def test_update_one_tag_in_list(self, mocker) -> None:
        """Updating one tag means sending the full list with the changed item."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.tags = ["Food consistency", "Cleanliness", "Wait time"]
        mock_config.rules = {"context": "test"}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        # "Cleanliness" → "Kitchen cleanliness" (send full updated list)
        request = UpdateMonitoringConfigRequest(
            tags=["Food consistency", "Kitchen cleanliness", "Wait time"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        assert update_call.kwargs.get("tags") == [
            "Food consistency",
            "Kitchen cleanliness",
            "Wait time",
        ]

    @pytest.mark.asyncio
    async def test_remove_one_tag_from_list(self, mocker) -> None:
        """Removing one tag means sending the list without that item."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.tags = ["Food consistency", "Cleanliness", "Wait time"]
        mock_config.rules = {"context": "test"}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        # Remove "Cleanliness" — send list without it
        request = UpdateMonitoringConfigRequest(
            tags=["Food consistency", "Wait time"],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        assert update_call.kwargs.get("tags") == ["Food consistency", "Wait time"]

    @pytest.mark.asyncio
    async def test_clear_all_tags(self, mocker) -> None:
        """Passing empty list should clear all tags."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.tags = ["Food consistency", "Cleanliness"]
        mock_config.rules = {"context": "test"}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            tags=[],
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )

        await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        update_call = mock_config_repo.return_value.update.call_args
        assert update_call.kwargs.get("tags") == []

    @pytest.mark.asyncio
    async def test_tags_none_leaves_unchanged(self, mocker) -> None:
        """When tags is None (omitted), no update should be made at all."""
        from services.monitoring_service._implementation import update_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_project = MagicMock()
        mocker.patch(
            "services.monitoring_service._implementation.ProjectRepositoryAsync"
        ).return_value.get_project = AsyncMock(return_value=mock_project)

        mock_config = MagicMock()
        mock_config.project_id = project_id
        mock_config.name = "Test"
        mock_config.tags = ["Existing tag"]
        mock_config.rules = {"context": "test"}

        mock_config_repo = mocker.patch(
            "services.monitoring_service._implementation.MonitoringConfigRepositoryAsync"
        )
        mock_config_repo.return_value.get_by_id = AsyncMock(return_value=mock_config)
        mock_config_repo.return_value.get_by_name = AsyncMock(return_value=None)
        mock_config_repo.return_value.update = AsyncMock(return_value=MagicMock())

        request = UpdateMonitoringConfigRequest(
            tags=None,
            name=None,
            description=None,
            context=None,
            prompt=None,
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
        )

        result = await update_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )

        # No fields changed → update should NOT be called, returns original config
        mock_config_repo.return_value.update.assert_not_called()
        assert result[0] == mock_config


class TestBuildConfigResponseTags:
    """Test that build_config_response includes tags."""

    @pytest.mark.asyncio
    async def test_tags_included_in_response(self) -> None:
        """Tags from the config should appear in the response."""
        from services.monitoring_service._implementation import build_config_response

        now = datetime.now(tz=timezone.utc)
        mock_config = MagicMock()
        mock_config.id = uuid.uuid4()
        mock_config.project_id = uuid.uuid4()
        mock_config.signal_source_id = uuid.uuid4()
        mock_config.name = "Test"
        mock_config.description = None
        mock_config.rules = {"context": "test", "reference_images": []}
        mock_config.tags = ["Food consistency", "Cleanliness"]
        mock_config.enabled = True
        mock_config.created_at = now
        mock_config.updated_at = now

        response = await build_config_response(mock_config)
        assert response.tags == ["Food consistency", "Cleanliness"]

    @pytest.mark.asyncio
    async def test_none_tags_returns_empty_list(self) -> None:
        """When config.tags is None, response should return empty list."""
        from services.monitoring_service._implementation import build_config_response

        now = datetime.now(tz=timezone.utc)
        mock_config = MagicMock()
        mock_config.id = uuid.uuid4()
        mock_config.project_id = uuid.uuid4()
        mock_config.signal_source_id = uuid.uuid4()
        mock_config.name = "Test"
        mock_config.description = None
        mock_config.rules = {"context": "test", "reference_images": []}
        mock_config.tags = None
        mock_config.enabled = True
        mock_config.created_at = now
        mock_config.updated_at = now

        response = await build_config_response(mock_config)
        assert response.tags == []
