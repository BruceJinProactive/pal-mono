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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
                tags=None,
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
            tags=None,
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
                tags=None,
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
                tags=None,
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
    async def test_update_images_parses_and_merges_with_legacy_descriptions(
        self, mocker
    ) -> None:
        """Route should parse update_images and merge with update_descriptions."""
        from api.routes.operation import update_monitoring_config

        mock_result = MagicMock()
        mock_update = mocker.patch(
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
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
            add_images=[],
            add_descriptions=[],
            add_image_flags=[],
            remove_image_ids=[],
            update_descriptions=['{"id":"img-1","description":"legacy desc"}'],
            update_images=['{"id":"img-1","flag":"fail"}'],
            user_context=MagicMock(),
            session=AsyncMock(),
        )

        assert result == mock_result
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["update_image_metadata"] == {
            "img-1": {"description": "legacy desc", "flag": "fail"}
        }

    @pytest.mark.asyncio
    async def test_invalid_update_images_flag_raises_400(self) -> None:
        """Should raise 400 when update_images contains an invalid flag."""
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
                tags=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                update_images=['{"id":"img-1","flag":"bad"}'],
                user_context=MagicMock(),
                session=AsyncMock(),
            )

        assert exc_info.value.status_code == 400
        assert "update_images" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_update_images_entry_must_be_object_raises_400(self) -> None:
        """Should raise 400 when update_images entry is not a JSON object."""
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
                tags=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                update_images=['"not-an-object"'],
                user_context=MagicMock(),
                session=AsyncMock(),
            )

        assert exc_info.value.status_code == 400
        assert "update_images" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_update_images_missing_id_raises_400(self) -> None:
        """Should raise 400 when update_images entry omits required id."""
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
                tags=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                update_images=['{"description":"new"}'],
                user_context=MagicMock(),
                session=AsyncMock(),
            )

        assert exc_info.value.status_code == 400
        assert "update_images" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_update_images_requires_description_or_flag_raises_400(self) -> None:
        """Should raise 400 when update_images has id but no mutable fields."""
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
                tags=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                update_images=['{"id":"img-1"}'],
                user_context=MagicMock(),
                session=AsyncMock(),
            )

        assert exc_info.value.status_code == 400
        assert "update_images" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_update_images_json_raises_400(self) -> None:
        """Should raise 400 when update_images contains invalid JSON."""
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
                tags=None,
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                update_images=["{bad-json"],
                user_context=MagicMock(),
                session=AsyncMock(),
            )

        assert exc_info.value.status_code == 400
        assert "invalid json in update_images" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_update_images_description_only_reaches_downstream(
        self, mocker
    ) -> None:
        """Description-only update_images entry should be accepted."""
        from api.routes.operation import update_monitoring_config

        mock_result = MagicMock()
        mock_update = mocker.patch(
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
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags=None,
            add_images=[],
            add_descriptions=[],
            add_image_flags=[],
            remove_image_ids=[],
            update_descriptions=[],
            update_images=['{"id":"img-1","description":"updated"}'],
            user_context=MagicMock(),
            session=AsyncMock(),
        )

        assert result == mock_result
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["update_image_metadata"] == {
            "img-1": {"description": "updated"}
        }

    @pytest.mark.asyncio
    async def test_direct_call_omitting_update_lists_is_normalized(
        self, mocker
    ) -> None:
        """Direct function calls should normalize default Form values to empty lists."""
        from api.routes.operation import update_monitoring_config

        mock_result = MagicMock()
        mock_update = mocker.patch(
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
            tags=None,
            add_images=[],
            add_descriptions=[],
            add_image_flags=[],
            remove_image_ids=[],
            user_context=MagicMock(),
            session=AsyncMock(),
        )

        assert result == mock_result
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["update_image_metadata"] == {}


# ---------------------------------------------------------------------------
# Tags validation tests (create + update)
# ---------------------------------------------------------------------------


class TestCreateTagsValidation:
    """Tags JSON parsing validation in create_monitoring_config."""

    @pytest.mark.asyncio
    async def test_invalid_tags_json_raises_400(self) -> None:
        """Should raise 400 when tags is not valid JSON."""
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
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=True,
                tags="not-valid-json{",
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "tags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_tags_not_list_of_strings_raises_400(self) -> None:
        """Should raise 400 when tags is valid JSON but not a list of strings."""
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
                fail_criteria=None,
                structured_output=None,
                model=None,
                enabled=True,
                tags='{"key": "value"}',
                monitoring_time_window=None,
                reference_images=[],
                reference_image_descriptions=[],
                reference_image_flags=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "tags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_valid_tags_parsed_successfully(self, mocker) -> None:
        """Valid tags JSON should parse and reach service layer."""
        from api.routes.operation import create_monitoring_config

        mock_result = MagicMock()
        mock_create = mocker.patch(
            "api.routes.operation._monitoring.create_monitoring_config",
            new_callable=AsyncMock,
            return_value=mock_result,
        )

        result = await create_monitoring_config(
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
            tags='["Food consistency", "Cleanliness"]',
            monitoring_time_window=None,
            reference_images=[],
            reference_image_descriptions=[],
            reference_image_flags=[],
            user_context=MagicMock(),
            session=AsyncMock(),
        )
        assert result == mock_result
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["request"].tags == ["Food consistency", "Cleanliness"]


class TestUpdateTagsValidation:
    """Tags JSON parsing validation in update_monitoring_config."""

    @pytest.mark.asyncio
    async def test_invalid_tags_json_raises_400(self) -> None:
        """Should raise 400 when tags is not valid JSON."""
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
                tags="bad-json!",
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "tags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_tags_not_list_of_strings_raises_400(self) -> None:
        """Should raise 400 when tags is valid JSON but not a list of strings."""
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
                tags="42",
                add_images=[],
                add_descriptions=[],
                add_image_flags=[],
                remove_image_ids=[],
                update_descriptions=[],
                user_context=MagicMock(),
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 400
        assert "tags" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_valid_tags_parsed_successfully(self, mocker) -> None:
        """Valid tags JSON should parse and reach service layer."""
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
            pass_criteria=None,
            fail_criteria=None,
            structured_output=None,
            model=None,
            enabled=None,
            monitoring_time_window=None,
            tags='["Food consistency"]',
            add_images=[],
            add_descriptions=[],
            add_image_flags=[],
            remove_image_ids=[],
            update_descriptions=[],
            user_context=MagicMock(),
            session=AsyncMock(),
        )
        assert result == mock_result
