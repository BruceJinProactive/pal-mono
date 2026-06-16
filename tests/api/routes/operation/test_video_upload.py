"""Tests for video upload with MKV-to-MP4 remux."""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from pytest_mock import MockerFixture


def _patch_camera_lookup(mocker: MockerFixture) -> None:
    mocker.patch(
        "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
        new_callable=AsyncMock,
        return_value=MagicMock(),
    )


def _patch_s3_client(mocker: MockerFixture) -> MagicMock:
    mock_s3 = MagicMock()
    mocker.patch(
        "api.routes.operation._video_upload.boto3.client",
        return_value=mock_s3,
    )
    return mock_s3


def _archive_frame_payloads() -> list[dict]:
    return [
        {"jpeg_bytes": b"a" * 200, "timestamp_seconds": 15.0},
        {"jpeg_bytes": b"b" * 200, "timestamp_seconds": 30.0},
        {"jpeg_bytes": b"c" * 200, "timestamp_seconds": 45.0},
        {"jpeg_bytes": b"d" * 200, "timestamp_seconds": 60.0},
    ]


def _patch_archive_frame_extraction(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "api.routes.operation._video_upload.extract_one_minute_video_frames_from_bytes",
        return_value=(60.0, _archive_frame_payloads()),
    )


class TestUploadArchiveFrames:
    """Tests for archive frame S3 uploads derived from one-minute videos."""

    @pytest.mark.asyncio
    async def test_uses_source_timestamp_for_frame_key_but_keeps_requested_label(
        self, mocker: MockerFixture
    ) -> None:
        from api.routes.operation._video_upload import _upload_archive_frames

        mocker.patch(
            "api.routes.operation._video_upload.AWS_IMAGE_BUCKET_NAME",
            "image-bucket",
        )
        mock_s3 = MagicMock()

        frame_keys = await _upload_archive_frames(
            s3_client=mock_s3,
            account_id="acc-1",
            project_id="proj-1",
            camera_id="cam-1",
            video_filename="2026-06-16_12-00-00.mp4",
            video_s3_key="security/cameras/acc-1/proj-1/cam-1/videos/2026-06-16/2026-06-16_12-00-00.mp4",
            frames=[
                {
                    "jpeg_bytes": b"x" * 200,
                    "timestamp_seconds": 60.0,
                    "source_timestamp_seconds": 59.95,
                }
            ],
            upload_time=datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
        )

        assert frame_keys == [
            "security/cameras/acc-1/proj-1/cam-1/images/2026-06-16/2026-06-16_12-00-59.jpg"
        ]
        call_args = mock_s3.upload_fileobj.call_args
        assert call_args[0][1] == "image-bucket"
        assert call_args[0][2] == frame_keys[0]
        mock_s3.head_object.assert_called_once_with(
            Bucket="image-bucket",
            Key=frame_keys[0],
        )
        metadata = call_args[1]["ExtraArgs"]["Metadata"]
        assert metadata["timestamp_seconds"] == "60"
        assert metadata["source_timestamp_seconds"] == "59.95"

    @pytest.mark.asyncio
    async def test_retrieval_verification_failure_logs_without_failing_upload(
        self, mocker: MockerFixture
    ) -> None:
        from api.routes.operation._video_upload import _upload_archive_frames

        mocker.patch(
            "api.routes.operation._video_upload.AWS_IMAGE_BUCKET_NAME",
            "image-bucket",
        )
        mock_warning = mocker.patch("api.routes.operation._video_upload.logger.warning")
        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = Exception("head failed")

        frame_keys = await _upload_archive_frames(
            s3_client=mock_s3,
            account_id="acc-1",
            project_id="proj-1",
            camera_id="cam-1",
            video_filename="2026-06-16_12-00-00.mp4",
            video_s3_key="security/cameras/acc-1/proj-1/cam-1/videos/2026-06-16/2026-06-16_12-00-00.mp4",
            frames=[
                {
                    "jpeg_bytes": b"x" * 200,
                    "timestamp_seconds": 15.0,
                }
            ],
            upload_time=datetime(2026, 6, 16, 13, 0, tzinfo=timezone.utc),
        )

        assert frame_keys == [
            "security/cameras/acc-1/proj-1/cam-1/images/2026-06-16/2026-06-16_12-00-15.jpg"
        ]
        mock_s3.upload_fileobj.assert_called_once()
        mock_warning.assert_called_once()


class TestVideoUploadSizeLimitHelpers:
    """Tests for environment-backed video size limit helpers."""

    def test_read_positive_int_env_returns_valid_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api.routes.operation import _video_upload

        monkeypatch.setenv("PAL_TEST_VIDEO_LIMIT", "123")

        assert _video_upload._read_positive_int_env("PAL_TEST_VIDEO_LIMIT", 5) == 123

    @pytest.mark.parametrize("env_value", ["invalid", "0", "-1"])
    def test_read_positive_int_env_uses_default_for_invalid_values(
        self, monkeypatch: pytest.MonkeyPatch, env_value: str
    ) -> None:
        from api.routes.operation import _video_upload

        monkeypatch.setenv("PAL_TEST_VIDEO_LIMIT", env_value)

        assert _video_upload._read_positive_int_env("PAL_TEST_VIDEO_LIMIT", 5) == 5

    def test_read_optional_max_size_env_returns_valid_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from api.routes.operation import _video_upload

        monkeypatch.setenv("PAL_TEST_ARCHIVE_LIMIT", "456")

        assert (
            _video_upload._read_optional_max_size_env("PAL_TEST_ARCHIVE_LIMIT") == 456
        )

    @pytest.mark.parametrize("env_value", ["invalid", "-1", "0", ""])
    def test_read_optional_max_size_env_returns_none_for_disabled_values(
        self, monkeypatch: pytest.MonkeyPatch, env_value: str
    ) -> None:
        from api.routes.operation import _video_upload

        monkeypatch.setenv("PAL_TEST_ARCHIVE_LIMIT", env_value)

        assert (
            _video_upload._read_optional_max_size_env("PAL_TEST_ARCHIVE_LIMIT") is None
        )

    def test_format_size_limit_uses_mb_for_even_mib_values(self) -> None:
        from api.routes.operation import _video_upload

        assert _video_upload._format_size_limit(2 * 1024 * 1024) == "2MB"

    def test_format_size_limit_uses_bytes_for_partial_mib_values(self) -> None:
        from api.routes.operation import _video_upload

        assert _video_upload._format_size_limit(123) == "123 bytes"


class TestUploadCameraVideoRemux:
    """Tests for MKV/AVI/WebM to MP4 remux during upload."""

    @pytest.mark.asyncio
    async def test_mkv_file_is_remuxed_to_mp4(self, mocker):
        """Should remux MKV to MP4 and upload with .mp4 extension."""
        from api.routes.operation._video_upload import upload_camera_video

        original_bytes = b"fake-mkv-data"
        remuxed_bytes = b"fake-mp4-data"

        video_file = BytesIO(original_bytes)
        upload = UploadFile(
            filename="recording.mkv", file=video_file, size=len(original_bytes)
        )

        session = AsyncMock()
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mock_remux = mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
            return_value=remuxed_bytes,
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video("acc-1", "proj-1", "cam-1", upload, session)

        mock_remux.assert_called_once_with(original_bytes)
        # S3 key should have .mp4 extension
        assert result.url.endswith(".mp4")
        assert not result.url.endswith(".mkv")
        # Should upload the remuxed bytes
        call_args = mock_s3.upload_fileobj.call_args
        uploaded_file = call_args[0][0]
        assert uploaded_file.read() == remuxed_bytes
        # Content type should be mp4
        assert call_args[1]["ExtraArgs"]["ContentType"] == "video/mp4"

    @pytest.mark.asyncio
    async def test_mp4_file_is_not_remuxed(self, mocker):
        """Should upload MP4 files directly without remuxing."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"mp4-data")
        upload = UploadFile(filename="recording.mp4", file=video_file, size=8)

        session = AsyncMock()
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mock_remux = mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video("acc-1", "proj-1", "cam-1", upload, session)

        mock_remux.assert_not_called()
        assert result.url.endswith(".mp4")

    @pytest.mark.asyncio
    async def test_remux_failure_falls_back_to_original(self, mocker):
        """Should upload original file if remux fails."""
        from api.routes.operation._video_upload import upload_camera_video

        original_bytes = b"fake-mkv-data"
        video_file = BytesIO(original_bytes)
        upload = UploadFile(
            filename="recording.mkv", file=video_file, size=len(original_bytes)
        )

        session = AsyncMock()
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
            side_effect=Exception("remux failed"),
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video("acc-1", "proj-1", "cam-1", upload, session)

        # Should still upload successfully with original extension
        assert result.url.endswith(".mkv")
        # Should have called upload_fileobj (didn't crash)
        mock_s3.upload_fileobj.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_mkv_file_skips_remux(self, mocker):
        """Should upload original file without remuxing when upload is empty."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"")
        upload = UploadFile(filename="recording.mkv", file=video_file, size=0)

        session = AsyncMock()
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mock_remux = mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video("acc-1", "proj-1", "cam-1", upload, session)

        mock_remux.assert_not_called()
        assert result.url.endswith(".mkv")
        call_args = mock_s3.upload_fileobj.call_args
        uploaded_file = call_args[0][0]
        assert uploaded_file.read() == b""

    @pytest.mark.asyncio
    async def test_avi_file_is_remuxed(self, mocker):
        """Should remux AVI files to MP4."""
        from api.routes.operation._video_upload import upload_camera_video

        original_bytes = b"fake-avi-data"
        remuxed_bytes = b"fake-mp4-data"

        video_file = BytesIO(original_bytes)
        upload = UploadFile(
            filename="recording.avi", file=video_file, size=len(original_bytes)
        )

        session = AsyncMock()
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mock_remux = mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
            return_value=remuxed_bytes,
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video("acc-1", "proj-1", "cam-1", upload, session)

        mock_remux.assert_called_once()
        assert result.url.endswith(".mp4")

    @pytest.mark.asyncio
    async def test_mov_file_is_not_remuxed(self, mocker):
        """Should upload MOV files directly (already Gemini-compatible)."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"mov-data")
        upload = UploadFile(filename="recording.mov", file=video_file, size=8)

        session = AsyncMock()
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mock_remux = mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video("acc-1", "proj-1", "cam-1", upload, session)

        mock_remux.assert_not_called()
        assert result.url.endswith(".mov")

    @pytest.mark.asyncio
    async def test_llm_analysis_false_keeps_shared_path_and_metadata(self, mocker):
        """Should keep the same S3 path and store llm_analysis metadata."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"mp4-data")
        upload = UploadFile(filename="recording.mp4", file=video_file, size=8)

        session = AsyncMock()
        mock_extract = _patch_archive_frame_extraction(mocker)
        mocker.patch(
            "api.routes.operation._video_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "api.routes.operation._video_upload.boto3.client",
            return_value=mock_s3,
        )

        result = await upload_camera_video(
            "acc-1",
            "proj-1",
            "cam-1",
            upload,
            session,
            llm_analysis=False,
        )

        assert len(result.url.split("/")) == 8
        assert result.url.endswith("/recording.mp4")
        mock_extract.assert_called_once_with(
            b"mp4-data",
            (15.0, 30.0, 45.0, 60.0),
        )
        call_args = mock_s3.upload_fileobj.call_args
        assert call_args[0][2] == result.url
        assert call_args[1]["ExtraArgs"]["Metadata"]["llm_analysis"] == "false"
        assert (
            call_args[1]["ExtraArgs"]["Metadata"]["archive_frame_timestamps_seconds"]
            == "15,30,45,60"
        )
        frame_keys = call_args[1]["ExtraArgs"]["Metadata"][
            "archive_frame_s3_keys"
        ].split(",")
        assert len(frame_keys) == 4
        assert all("/images/" in key for key in frame_keys)

    @pytest.mark.asyncio
    async def test_llm_analysis_rejects_file_above_analysis_limit(
        self, mocker: MockerFixture
    ) -> None:
        """Should keep the analysis upload cap for files sent to the LLM path."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"oversized")
        upload = UploadFile(filename="recording.mp4", file=video_file, size=9)

        session = AsyncMock()
        _patch_camera_lookup(mocker)
        mocker.patch(
            "api.routes.operation._video_upload.LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES",
            8,
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_video(
                "acc-1",
                "proj-1",
                "cam-1",
                upload,
                session,
                llm_analysis=True,
            )

        assert exc_info.value.status_code == 413
        assert "for LLM analysis" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_archive_upload_allows_file_above_analysis_limit(
        self, mocker: MockerFixture
    ) -> None:
        """Should not apply the LLM-analysis cap to archive-only uploads."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"oversized")
        upload = UploadFile(filename="recording.mp4", file=video_file, size=9)

        session = AsyncMock()
        _patch_camera_lookup(mocker)
        mock_s3 = _patch_s3_client(mocker)
        _patch_archive_frame_extraction(mocker)
        mocker.patch(
            "api.routes.operation._video_upload.LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES",
            8,
        )
        mocker.patch(
            "api.routes.operation._video_upload.ARCHIVE_MAX_VIDEO_SIZE_BYTES",
            None,
        )

        result = await upload_camera_video(
            "acc-1",
            "proj-1",
            "cam-1",
            upload,
            session,
            llm_analysis=False,
        )

        assert result.url.endswith("/recording.mp4")
        assert mock_s3.upload_fileobj.call_count == 5

    @pytest.mark.asyncio
    async def test_archive_upload_rejects_file_above_configured_archive_limit(
        self, mocker: MockerFixture
    ) -> None:
        """Should enforce the archive-only limit when one is configured."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"oversized")
        upload = UploadFile(filename="recording.mp4", file=video_file, size=9)

        session = AsyncMock()
        _patch_camera_lookup(mocker)
        mocker.patch(
            "api.routes.operation._video_upload.ARCHIVE_MAX_VIDEO_SIZE_BYTES",
            8,
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_video(
                "acc-1",
                "proj-1",
                "cam-1",
                upload,
                session,
                llm_analysis=False,
            )

        assert exc_info.value.status_code == 413
        assert "for archive-only upload" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_archive_mkv_upload_skips_remux(self, mocker: MockerFixture) -> None:
        """Should stream original MKV bytes for archive-only uploads."""
        from api.routes.operation._video_upload import upload_camera_video

        original_bytes = b"fake-mkv-data"
        video_file = BytesIO(original_bytes)
        upload = UploadFile(
            filename="recording.mkv", file=video_file, size=len(original_bytes)
        )

        session = AsyncMock()
        _patch_camera_lookup(mocker)
        mock_s3 = _patch_s3_client(mocker)
        _patch_archive_frame_extraction(mocker)
        mock_remux = mocker.patch(
            "api.routes.operation._video_upload.remux_to_mp4",
            return_value=b"fake-mp4-data",
        )

        result = await upload_camera_video(
            "acc-1",
            "proj-1",
            "cam-1",
            upload,
            session,
            llm_analysis=False,
        )

        assert result.url.endswith(".mkv")
        mock_remux.assert_not_called()
        call_args = mock_s3.upload_fileobj.call_args
        uploaded_file = call_args[0][0]
        assert uploaded_file.read() == original_bytes
        assert call_args[1]["ExtraArgs"]["ContentType"] == "video/x-matroska"
        assert call_args[1]["ExtraArgs"]["Metadata"]["llm_analysis"] == "false"

    @pytest.mark.asyncio
    async def test_archive_upload_rejects_non_one_minute_video(
        self, mocker: MockerFixture
    ) -> None:
        """Should reject archive-only videos that fail one-minute validation."""
        from api.routes.operation._video_upload import upload_camera_video

        video_file = BytesIO(b"mp4-data")
        upload = UploadFile(filename="recording.mp4", file=video_file, size=8)

        session = AsyncMock()
        _patch_camera_lookup(mocker)
        mock_s3 = _patch_s3_client(mocker)
        mocker.patch(
            "api.routes.operation._video_upload.extract_one_minute_video_frames_from_bytes",
            side_effect=ValueError(
                "Archive-only videos must be 60 seconds long (detected 45.00s)"
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_video(
                "acc-1",
                "proj-1",
                "cam-1",
                upload,
                session,
                llm_analysis=False,
            )

        assert exc_info.value.status_code == 400
        assert "60 seconds long" in str(exc_info.value.detail)
        mock_s3.upload_fileobj.assert_not_called()
