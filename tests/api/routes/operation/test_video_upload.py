"""Tests for video upload with MKV-to-MP4 remux."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile


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
