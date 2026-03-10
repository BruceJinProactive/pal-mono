"""Tests for monitoring config restructure — service layer.

Validates that upload_reference_images stores flag per image,
and that update_config handles context, pass_criteria, fail_criteria.
"""

import uuid
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
