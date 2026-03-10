"""Tests for monitoring config route-level validation.

Covers create_monitoring_config and update_monitoring_config validation logic
for context resolution, criteria JSON parsing, and reference image flag checks.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# create_monitoring_config tests
# ---------------------------------------------------------------------------


class TestCreateMonitoringConfigValidation:
    """Validation in create_monitoring_config route handler."""

    @pytest.mark.asyncio
    async def test_no_context_or_prompt_raises_400(self) -> None:
        """Should raise 400 when neither context nor prompt is provided."""
        from api.routes.operation import create_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context=None,
                prompt=None,
                pass_criteria=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert (
            "context" in str(exc_info.value.detail).lower()
            or "prompt" in str(exc_info.value.detail).lower()
        )

    @pytest.mark.asyncio
    async def test_invalid_pass_criteria_json_raises_400(self) -> None:
        """Should raise 400 when pass_criteria is not valid JSON."""
        from api.routes.operation import create_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context="test context",
                prompt=None,
                pass_criteria="not-valid-json{",
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "pass_criteria" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_fail_criteria_json_raises_400(self) -> None:
        """Should raise 400 when fail_criteria is not valid JSON."""
        from api.routes.operation import create_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context="test context",
                prompt=None,
                pass_criteria=None,
                fail_criteria="bad-json!",
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "fail_criteria" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_valid_criteria_parsed_then_flag_count_mismatch_raises_400(
        self,
    ) -> None:
        """Valid criteria JSON should parse, then flag count mismatch triggers 400."""
        from api.routes.operation import create_monitoring_config

        mock_image = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context="test context",
                prompt=None,
                pass_criteria='["clean surfaces"]',
                fail_criteria='["visible debris"]',
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[mock_image],
                reference_image_descriptions=["desc1"],
                reference_image_flags=["pass", "fail"],  # 2 flags, 1 image
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "flags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_flag_value_raises_400(self) -> None:
        """Should raise 400 when flag value is not 'pass' or 'fail'."""
        from api.routes.operation import create_monitoring_config

        mock_image = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context="test context",
                prompt=None,
                pass_criteria=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[mock_image],
                reference_image_descriptions=["desc1"],
                reference_image_flags=["invalid_flag"],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "invalid" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_pass_criteria_not_list_raises_400(self) -> None:
        """Should raise 400 when pass_criteria is valid JSON but not a list of strings."""
        from api.routes.operation import create_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context="test context",
                prompt=None,
                pass_criteria='"just a string"',
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "pass_criteria" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_fail_criteria_not_list_raises_400(self) -> None:
        """Should raise 400 when fail_criteria is valid JSON but not a list of strings."""
        from api.routes.operation import create_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await create_monitoring_config(
                project_id=uuid.uuid4(),
                signal_source_id=uuid.uuid4(),
                name="test",
                description=None,
                monitoring_context="test context",
                prompt=None,
                pass_criteria=None,
                fail_criteria='{"key": "value"}',
                structured_output=None,
                model=None,
                enabled=True,
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "fail_criteria" in str(exc_info.value.detail).lower()


# ---------------------------------------------------------------------------
# update_monitoring_config tests
# ---------------------------------------------------------------------------


class TestUpdateMonitoringConfigValidation:
    """Validation in update_monitoring_config route handler."""

    @pytest.mark.asyncio
    async def test_add_image_flags_count_mismatch_raises_400(self) -> None:
        """Should raise 400 when add_image_flags count != add_images count."""
        from api.routes.operation import update_monitoring_config

        mock_image = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await update_monitoring_config(
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                name=None,
                description=None,
                prompt=None,
                monitoring_context=None,
                pass_criteria=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
                add_images=[mock_image],
                add_descriptions=["desc1"],
                add_image_flags=["pass", "fail"],  # 2 flags, 1 image
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "add_image_flags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_add_image_flag_raises_400(self) -> None:
        """Should raise 400 when add_image_flag value is not 'pass' or 'fail'."""
        from api.routes.operation import update_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await update_monitoring_config(
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                name=None,
                description=None,
                prompt=None,
                monitoring_context=None,
                pass_criteria=None,
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
                add_images=[MagicMock()],
                add_descriptions=["desc1"],
                add_image_flags=["bad_value"],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "invalid" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_pass_criteria_json_raises_400(self) -> None:
        """Should raise 400 when pass_criteria is not valid JSON."""
        from api.routes.operation import update_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await update_monitoring_config(
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                name=None,
                description=None,
                prompt=None,
                monitoring_context=None,
                pass_criteria="not-valid{json",
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "pass_criteria" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_fail_criteria_json_raises_400(self) -> None:
        """Should raise 400 when fail_criteria is not valid JSON."""
        from api.routes.operation import update_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await update_monitoring_config(
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                name=None,
                description=None,
                prompt=None,
                monitoring_context=None,
                pass_criteria=None,
                fail_criteria="bad-json!",
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "fail_criteria" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_valid_criteria_parsed_then_reaches_downstream(self, mocker) -> None:
        """Valid criteria JSON should parse and proceed to service layer."""
        from api.routes.operation import update_monitoring_config

        mock_result = MagicMock()
        mocker.patch(
            "api.routes.operation._monitoring.update_monitoring_config",
            new_callable=AsyncMock,
            return_value=mock_result,
        )

        result = await update_monitoring_config(
            project_id=uuid.uuid4(),
            config_id=uuid.uuid4(),
            name=None,
            description=None,
            prompt=None,
            monitoring_context=None,
            pass_criteria='["criterion1"]',
            fail_criteria='["fail1"]',
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            add_images=[],
            add_descriptions=[],
            add_image_flags=[],
            remove_image_ids=[],
            update_descriptions=[],
            user_context=MagicMock(),
            session=AsyncMock(),
        )
        assert result == mock_result

    @pytest.mark.asyncio
    async def test_pass_criteria_not_list_raises_400(self) -> None:
        """Should raise 400 when pass_criteria is valid JSON but not a list of strings."""
        from api.routes.operation import update_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await update_monitoring_config(
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                name=None,
                description=None,
                prompt=None,
                monitoring_context=None,
                pass_criteria="42",
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "pass_criteria" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_fail_criteria_not_list_raises_400(self) -> None:
        """Should raise 400 when fail_criteria is valid JSON but not a list of strings."""
        from api.routes.operation import update_monitoring_config

        with pytest.raises(HTTPException) as exc_info:
            await update_monitoring_config(
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
                name=None,
                description=None,
                prompt=None,
                monitoring_context=None,
                pass_criteria=None,
                fail_criteria="[1, 2, 3]",
                structured_output=None,
                model=None,
                enabled=None,
                monitoring_time_window=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "fail_criteria" in str(exc_info.value.detail).lower()
