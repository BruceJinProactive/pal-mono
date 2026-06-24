"""Tests for video frame extraction logic."""

import base64
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from services.monitoring_service._video import (
    _MP4_COMPATIBLE_CODECS,
    _create_video_s3_client,
    _extract_frames_at_timestamps_sync,
    _extract_frames_sync,
    _lookup_camera_video_segments_sync,
    _validate_one_minute_duration,
    download_video_bytes,
    extract_one_minute_video_frames_from_bytes,
    extract_video_frames,
    lookup_camera_video_segments,
    remux_to_mp4,
)


def _mock_s3_client(
    pages_by_call: list[list[dict[str, Any]]],
) -> tuple[MagicMock, MagicMock]:
    s3_client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.side_effect = pages_by_call
    s3_client.get_paginator.return_value = paginator

    def fake_generate_presigned_url(
        _client_method: str,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str:
        return f"https://example.com/{ExpiresIn}/{Params['Key']}"

    s3_client.generate_presigned_url.side_effect = fake_generate_presigned_url
    return s3_client, paginator


class TestExtractFramesSync:
    """Tests for _extract_frames_sync — synchronous frame extraction."""

    def test_extracts_frames_at_intervals(self, mocker):
        """Should extract frames at the configured interval from the video."""
        # Create a mock frame that can be converted to image
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )

        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 30
        mock_stream.time_base = 1  # 1 second per unit
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.seek = MagicMock()
        # Return a fresh iterator each time decode is called
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()  # verify() doesn't raise
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)

        # Should have frames at 0, 10, 20 seconds (30s duration, 10s interval)
        assert len(frames) == 3

    def test_always_includes_frame_at_zero(self, mocker):
        """Should always include a frame at t=0."""
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 5
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)
        assert len(frames) >= 1
        assert frames[0]["timestamp_seconds"] == 0.0

    def test_generates_correct_timestamp_labels(self, mocker):
        """Should generate timestamp labels in M:SS format."""
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 70
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=30)

        # Frames at 0, 30, 60 seconds
        assert frames[0]["timestamp_label"] == "0:00"
        assert frames[1]["timestamp_label"] == "0:30"
        assert frames[2]["timestamp_label"] == "1:00"

    def test_returns_base64_data(self, mocker):
        """Should return base64-encoded JPEG data for each frame."""
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 5
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4")
        assert len(frames) >= 1
        # Verify the base64 data can be decoded
        decoded = base64.b64decode(frames[0]["base64_data"])
        assert decoded == b"x" * 200

    def test_handles_frame_extraction_failure_gracefully(self, mocker):
        """Should log warning and continue when a frame extraction fails."""
        mock_stream = MagicMock()
        mock_stream.duration = 20
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        # Raise an exception when trying to decode
        mock_container.decode.side_effect = Exception("decode error")

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Should not raise, just return empty list
        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)
        assert frames == []

    def test_zero_duration_video(self, mocker):
        """Should extract only frame at 0 for zero-duration video."""
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 0
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.duration = None
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4")
        assert len(frames) == 1
        assert frames[0]["timestamp_seconds"] == 0.0

    def test_falls_back_to_container_duration(self, mocker):
        """Should use container.duration when stream.duration is None."""
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = None
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        # 60 seconds in microseconds
        mock_container.duration = 60_000_000
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)

        # 60s video at 10s intervals: frames at 0, 10, 20, 30, 40, 50
        assert len(frames) == 6
        assert frames[0]["timestamp_seconds"] == 0.0
        assert frames[1]["timestamp_seconds"] == 10.0
        assert frames[5]["timestamp_seconds"] == 50.0

    def test_zero_duration_when_both_unavailable(self, mocker):
        """Should extract only 1 frame when both stream and container duration are None."""
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)  # Mock image dimensions
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(
                b"x" * 200
            )  # 200 bytes to pass validation
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = None
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.duration = None
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        # Mock Image.open to pass JPEG verification
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)
        assert len(frames) == 1
        assert frames[0]["timestamp_seconds"] == 0.0


class TestValidateOneMinuteDuration:
    """Tests for archive video duration bounds."""

    @pytest.mark.parametrize("duration_seconds", [59.0, 60.0, 61.89, 65.0])
    def test_accepts_duration_up_to_65_seconds(self, duration_seconds: float) -> None:
        _validate_one_minute_duration(duration_seconds)

    def test_rejects_unknown_duration(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            _validate_one_minute_duration(0.0)

        assert "Could not determine video duration" in str(exc_info.value)

    @pytest.mark.parametrize("duration_seconds", [58.99, 65.01])
    def test_rejects_duration_outside_bounds(self, duration_seconds: float) -> None:
        with pytest.raises(ValueError) as exc_info:
            _validate_one_minute_duration(duration_seconds)

        assert "between 59 and 65 seconds long" in str(exc_info.value)


class TestExtractFramesAtTimestampsSync:
    """Tests for exact timestamp extraction used by archive video uploads."""

    def test_extracts_archive_frames_and_validates_one_minute_duration(
        self, mocker
    ) -> None:
        mock_pil_image = MagicMock()
        mock_pil_image.size = (1920, 1080)
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"x" * 200)
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 60
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.seek = MagicMock()
        mock_container.decode = MagicMock(
            side_effect=lambda video=None, **kwargs: iter([mock_frame])
        )

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )
        mock_img = MagicMock()
        mock_img.verify = MagicMock()
        mocker.patch(
            "services.monitoring_service._video.Image.open",
            return_value=mock_img,
        )

        duration, frames = _extract_frames_at_timestamps_sync(
            "/fake/video.mp4",
            (15.0, 30.0, 45.0, 60.0),
            require_one_minute=True,
        )

        assert duration == 60.0
        assert [frame["timestamp_seconds"] for frame in frames] == [
            15.0,
            30.0,
            45.0,
            60.0,
        ]
        assert frames[-1]["timestamp_label"] == "1:00"
        assert frames[-1]["source_timestamp_seconds"] < 60.0
        assert all(frame["jpeg_bytes"] == b"x" * 200 for frame in frames)

    def test_rejects_non_one_minute_video(self, mocker) -> None:
        mock_stream = MagicMock()
        mock_stream.duration = 45
        mock_stream.time_base = 1

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        with pytest.raises(ValueError) as exc_info:
            _extract_frames_at_timestamps_sync(
                "/fake/video.mp4",
                (15.0, 30.0, 45.0, 60.0),
                require_one_minute=True,
            )

        assert "between 59 and 65 seconds long" in str(exc_info.value)

    def test_extract_one_minute_video_frames_from_bytes_writes_temp_file(
        self, mocker
    ) -> None:
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.video"
        mocker.patch(
            "services.monitoring_service._video.tempfile.NamedTemporaryFile",
            return_value=mock_tmp,
        )
        mock_extract = mocker.patch(
            "services.monitoring_service._video._extract_frames_at_timestamps_sync",
            return_value=(60.0, [{"jpeg_bytes": b"x" * 200}]),
        )
        mocker.patch(
            "services.monitoring_service._video.os.path.exists",
            return_value=True,
        )
        mock_unlink = mocker.patch("services.monitoring_service._video.os.unlink")

        result = extract_one_minute_video_frames_from_bytes(b"video-bytes")

        assert result == (60.0, [{"jpeg_bytes": b"x" * 200}])
        mock_tmp.write.assert_called_once_with(b"video-bytes")
        mock_extract.assert_called_once_with(
            "/tmp/test.video",
            (15.0, 30.0, 45.0, 60.0),
            require_one_minute=True,
        )
        mock_unlink.assert_called_once_with("/tmp/test.video")


class TestExtractVideoFrames:
    """Tests for extract_video_frames — async S3 download + extraction."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self, mocker):
        """Should download video from S3, extract frames, and return frame list."""
        mock_frames = [
            {"base64_data": "abc", "timestamp_seconds": 0.0, "timestamp_label": "0:00"}
        ]

        # Mock S3 client
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=MagicMock(),
        )

        # Mock tempfile
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.video"
        mocker.patch(
            "services.monitoring_service._video.tempfile.NamedTemporaryFile",
            return_value=mock_tmp,
        )

        # Mock asyncio.to_thread to just call the function synchronously
        async def mock_to_thread(func, *args, **kwargs):
            if func == _extract_frames_sync:
                return mock_frames
            # For S3 download, just return None
            return None

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )

        # Mock os.path.exists and os.unlink for cleanup
        mocker.patch(
            "services.monitoring_service._video.os.path.exists", return_value=True
        )
        mocker.patch("services.monitoring_service._video.os.unlink")

        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        result = await extract_video_frames("test-key.mp4")
        assert result == mock_frames

    @pytest.mark.asyncio
    async def test_no_frames_extracted_raises_400(self, mocker):
        """Should raise HTTPException 400 when no frames could be extracted."""
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=MagicMock(),
        )

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.video"
        mocker.patch(
            "services.monitoring_service._video.tempfile.NamedTemporaryFile",
            return_value=mock_tmp,
        )

        async def mock_to_thread(func, *args, **kwargs):
            if func == _extract_frames_sync:
                return []  # No frames
            return None

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )

        mocker.patch(
            "services.monitoring_service._video.os.path.exists", return_value=True
        )
        mocker.patch("services.monitoring_service._video.os.unlink")
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        with pytest.raises(HTTPException) as exc_info:
            await extract_video_frames("test-key.mp4")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_s3_download_failure_raises_500(self, mocker):
        """Should raise HTTPException 500 when S3 download fails."""
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=MagicMock(),
        )

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.video"
        mocker.patch(
            "services.monitoring_service._video.tempfile.NamedTemporaryFile",
            return_value=mock_tmp,
        )

        async def mock_to_thread(func, *args, **kwargs):
            raise Exception("S3 download failed")

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )

        mocker.patch(
            "services.monitoring_service._video.os.path.exists", return_value=True
        )
        mocker.patch("services.monitoring_service._video.os.unlink")
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        with pytest.raises(HTTPException) as exc_info:
            await extract_video_frames("test-key.mp4")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_temp_file_cleaned_up_on_success(self, mocker):
        """Should clean up temp file after successful extraction."""
        mock_frames = [
            {"base64_data": "abc", "timestamp_seconds": 0.0, "timestamp_label": "0:00"}
        ]

        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=MagicMock(),
        )

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.video"
        mocker.patch(
            "services.monitoring_service._video.tempfile.NamedTemporaryFile",
            return_value=mock_tmp,
        )

        async def mock_to_thread(func, *args, **kwargs):
            if func == _extract_frames_sync:
                return mock_frames
            return None

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )

        mocker.patch(
            "services.monitoring_service._video.os.path.exists", return_value=True
        )
        mock_unlink = mocker.patch("services.monitoring_service._video.os.unlink")
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        await extract_video_frames("test-key.mp4")
        mock_unlink.assert_called_once_with("/tmp/test.video")

    @pytest.mark.asyncio
    async def test_temp_file_cleaned_up_on_failure(self, mocker):
        """Should clean up temp file even when extraction fails."""
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=MagicMock(),
        )

        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.video"
        mocker.patch(
            "services.monitoring_service._video.tempfile.NamedTemporaryFile",
            return_value=mock_tmp,
        )

        async def mock_to_thread(func, *args, **kwargs):
            raise Exception("extraction failed")

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )

        mocker.patch(
            "services.monitoring_service._video.os.path.exists", return_value=True
        )
        mock_unlink = mocker.patch("services.monitoring_service._video.os.unlink")
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        with pytest.raises(HTTPException):
            await extract_video_frames("test-key.mp4")

        mock_unlink.assert_called_once_with("/tmp/test.video")


class TestDownloadVideoBytes:
    """Tests for download_video_bytes — async S3 download returning raw bytes."""

    @pytest.mark.asyncio
    async def test_successful_download_with_content_type(self, mocker):
        """Should return video bytes and MIME type from S3 ContentType."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake-video-bytes"
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "video/mp4",
        }
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=mock_s3,
        )

        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        video_bytes, mime_type = await download_video_bytes("path/to/video.mp4")
        assert video_bytes == b"fake-video-bytes"
        assert mime_type == "video/mp4"

    @pytest.mark.asyncio
    async def test_mime_type_from_extension_when_no_content_type(self, mocker):
        """Should infer MIME type from file extension when ContentType is not video."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"fake-video"
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/octet-stream",
        }
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=mock_s3,
        )

        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        _, mime_type = await download_video_bytes("path/to/video.webm")
        assert mime_type == "video/webm"

    @pytest.mark.asyncio
    async def test_defaults_to_mp4_for_unknown_extension(self, mocker):
        """Should default to video/mp4 for unknown file extensions."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "",
        }
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=mock_s3,
        )

        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        _, mime_type = await download_video_bytes("path/to/video.xyz")
        assert mime_type == "video/mp4"

    @pytest.mark.asyncio
    async def test_s3_failure_raises_500(self, mocker):
        """Should raise HTTPException 500 when S3 download fails."""
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=MagicMock(),
        )

        async def mock_to_thread(func, *args, **kwargs):
            raise Exception("S3 error")

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        with pytest.raises(HTTPException) as exc_info:
            await download_video_bytes("path/to/video.mp4")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_mov_extension_returns_quicktime_mime(self, mocker):
        """Should return video/quicktime for .mov files."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"data"
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "",
        }
        mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=mock_s3,
        )

        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            side_effect=mock_to_thread,
        )
        mocker.patch(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "test-bucket",
        )

        _, mime_type = await download_video_bytes("path/to/video.mov")
        assert mime_type == "video/quicktime"


class TestRemuxToMp4:
    """Tests for remux_to_mp4 — MKV/AVI/WebM to MP4 container conversion."""

    def test_remux_h264_copies_packets(self, mocker):
        """Should remux H.264 video without re-encoding (copy packets)."""
        mock_src_stream = MagicMock()
        mock_src_stream.codec_context.name = "h264"
        mock_src_stream.average_rate = 30

        mock_packet = MagicMock()
        mock_packet.dts = 100

        mock_input_container = MagicMock()
        mock_input_container.streams.video = [mock_src_stream]
        mock_input_container.streams.audio = []
        mock_input_container.demux.return_value = iter([mock_packet])

        mock_out_stream = MagicMock()
        mock_output_container = MagicMock()
        mock_output_container.add_stream_from_template.return_value = mock_out_stream

        mocker.patch(
            "services.monitoring_service._video.av.open",
            side_effect=[mock_input_container, mock_output_container],
        )

        result = remux_to_mp4(b"fake-mkv-bytes")

        # Should use add_stream_from_template (remux), not add_stream (re-encode)
        mock_output_container.add_stream_from_template.assert_called_once_with(
            mock_src_stream
        )
        mock_output_container.mux.assert_called()
        assert isinstance(result, bytes)

    def test_remux_vp9_reencodes_to_h264(self, mocker):
        """Should re-encode VP9 video to H.264 since VP9 is not MP4-compatible."""
        mock_src_stream = MagicMock()
        mock_src_stream.codec_context.name = "vp9"
        mock_src_stream.codec_context.width = 1920
        mock_src_stream.codec_context.height = 1080
        mock_src_stream.average_rate = 30

        mock_frame = MagicMock()
        mock_encoded_packet = MagicMock()

        mock_input_container = MagicMock()
        mock_input_container.streams.video = [mock_src_stream]
        mock_input_container.streams.audio = []
        mock_input_container.decode.return_value = iter([mock_frame])

        mock_out_stream = MagicMock()
        mock_out_stream.encode.side_effect = [
            [mock_encoded_packet],  # encode(frame)
            [],  # flush
        ]

        mock_output_container = MagicMock()
        mock_output_container.add_stream.return_value = mock_out_stream

        mocker.patch(
            "services.monitoring_service._video.av.open",
            side_effect=[mock_input_container, mock_output_container],
        )

        result = remux_to_mp4(b"fake-webm-bytes")

        # Should add stream with libx264 codec (re-encode)
        mock_output_container.add_stream.assert_called_once_with("libx264", rate=30)
        assert mock_out_stream.width == 1920
        assert mock_out_stream.height == 1080
        assert isinstance(result, bytes)

    def test_raises_on_no_video_stream(self, mocker):
        """Should raise ValueError when source has no video stream."""
        mock_input_container = MagicMock()
        mock_input_container.streams.video = []

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_input_container,
        )

        with pytest.raises(ValueError, match="no video stream"):
            remux_to_mp4(b"bad-data")

    def test_mp4_compatible_codecs_set(self):
        """Should include common surveillance camera codecs."""
        assert "h264" in _MP4_COMPATIBLE_CODECS
        assert "hevc" in _MP4_COMPATIBLE_CODECS
        assert "h265" in _MP4_COMPATIBLE_CODECS
        # VP8/VP9 should NOT be compatible
        assert "vp8" not in _MP4_COMPATIBLE_CODECS
        assert "vp9" not in _MP4_COMPATIBLE_CODECS

    def test_containers_closed_on_success(self, mocker):
        """Should close both input and output containers."""
        mock_src_stream = MagicMock()
        mock_src_stream.codec_context.name = "h264"

        mock_input_container = MagicMock()
        mock_input_container.streams.video = [mock_src_stream]
        mock_input_container.streams.audio = []
        mock_input_container.demux.return_value = iter([])

        mock_output_container = MagicMock()
        mock_output_container.add_stream_from_template.return_value = MagicMock()

        mocker.patch(
            "services.monitoring_service._video.av.open",
            side_effect=[mock_input_container, mock_output_container],
        )

        remux_to_mp4(b"data")

        mock_input_container.close.assert_called_once()
        mock_output_container.close.assert_called_once()


class TestLookupCameraVideoSegments:
    """Tests for archive video lookup by event window."""

    def test_create_video_s3_client_uses_local_credentials(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker,
    ) -> None:
        monkeypatch.setenv("LOCAL_AWS_ACCESS_KEY_ID", "access-key")
        monkeypatch.setenv("LOCAL_AWS_SECRET_ACCESS_KEY", "secret-key")
        monkeypatch.setenv("LOCAL_AWS_SESSION_TOKEN", "session-token")
        mock_client = MagicMock()
        mock_boto_client = mocker.patch(
            "services.monitoring_service._video.boto3.client",
            return_value=mock_client,
        )

        result = _create_video_s3_client()

        assert result is mock_client
        mock_boto_client.assert_called_once_with(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="access-key",
            aws_secret_access_key="secret-key",
            aws_session_token="session-token",
        )

    def test_includes_timestamped_videos_with_nonzero_seconds(self) -> None:
        s3_client, _paginator = _mock_s3_client(
            [
                [
                    {
                        "Contents": [
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-04-37.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-05-03.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-22-03.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-22-43.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/not-a-timestamp.mp4"
                                )
                            },
                        ]
                    }
                ]
            ]
        )

        videos = _lookup_camera_video_segments_sync(
            s3_client=s3_client,
            bucket_name="bucket",
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, 37, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 22, 43, tzinfo=timezone.utc),
            segment_duration_seconds=60.0,
        )

        assert [video.s3_key.rsplit("/", 1)[-1] for video in videos] == [
            "2026-06-23_14-05-03.mp4",
            "2026-06-23_14-22-03.mp4",
        ]
        assert videos[0].segment_start_time == datetime(
            2026,
            6,
            23,
            14,
            5,
            3,
            tzinfo=timezone.utc,
        )
        assert videos[0].url.endswith("2026-06-23_14-05-03.mp4")

    def test_stops_after_max_segments(self) -> None:
        s3_client, _paginator = _mock_s3_client(
            [
                [
                    {
                        "Contents": [
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-05-00.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-06-00.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-07-00.mp4"
                                )
                            },
                        ]
                    }
                ]
            ]
        )

        videos = _lookup_camera_video_segments_sync(
            s3_client=s3_client,
            bucket_name="bucket",
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 8, tzinfo=timezone.utc),
            segment_duration_seconds=60.0,
            max_segments=2,
        )

        assert [video.s3_key.rsplit("/", 1)[-1] for video in videos] == [
            "2026-06-23_14-05-00.mp4",
            "2026-06-23_14-06-00.mp4",
        ]
        assert s3_client.generate_presigned_url.call_count == 2

    def test_lists_previous_day_for_segments_that_overlap_midnight(self) -> None:
        s3_client, paginator = _mock_s3_client(
            [
                [
                    {
                        "Contents": [
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_23-59-30.mp4"
                                )
                            }
                        ]
                    }
                ],
                [
                    {
                        "Contents": [
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-24/2026-06-24_00-00-30.mp4"
                                )
                            }
                        ]
                    }
                ],
            ]
        )

        videos = _lookup_camera_video_segments_sync(
            s3_client=s3_client,
            bucket_name="bucket",
            video_prefix="security/cameras/account/project/camera/videos",
            start_time=datetime(2026, 6, 24, 0, 0, 15, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 24, 0, 1, 15, tzinfo=timezone.utc),
            segment_duration_seconds=60.0,
        )

        assert len(videos) == 2
        assert (
            paginator.paginate.call_args_list[0]
            .kwargs["Prefix"]
            .endswith("videos/2026-06-23/")
        )
        assert (
            paginator.paginate.call_args_list[1]
            .kwargs["Prefix"]
            .endswith("videos/2026-06-24/")
        )

    def test_skips_invalid_keys_and_unusable_presigned_urls(self) -> None:
        s3_client, _paginator = _mock_s3_client(
            [
                [
                    {
                        "Contents": [
                            {"Key": None},
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-13-23_14-05-03.mp4"
                                )
                            },
                            {
                                "Key": (
                                    "security/cameras/account/project/camera/videos/"
                                    "2026-06-23/2026-06-23_14-05-03.mp4"
                                )
                            },
                        ]
                    }
                ]
            ]
        )
        s3_client.generate_presigned_url.return_value = ""
        s3_client.generate_presigned_url.side_effect = None

        videos = _lookup_camera_video_segments_sync(
            s3_client=s3_client,
            bucket_name="bucket",
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 6, tzinfo=timezone.utc),
            segment_duration_seconds=60.0,
        )

        assert videos == []

    @pytest.mark.asyncio
    async def test_async_lookup_returns_empty_without_bucket(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            None,
        )

        videos = await lookup_camera_video_segments(
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 6, tzinfo=timezone.utc),
        )

        assert videos == []

    @pytest.mark.asyncio
    async def test_async_lookup_returns_empty_for_invalid_duration(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "bucket",
        )

        videos = await lookup_camera_video_segments(
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 6, tzinfo=timezone.utc),
            segment_duration_seconds=0,
        )

        assert videos == []

    @pytest.mark.asyncio
    async def test_async_lookup_returns_empty_for_invalid_max_segments(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker,
    ) -> None:
        monkeypatch.setattr(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "bucket",
        )
        mock_create_client = mocker.patch(
            "services.monitoring_service._video._create_video_s3_client"
        )

        videos = await lookup_camera_video_segments(
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 6, tzinfo=timezone.utc),
            max_segments=0,
        )

        assert videos == []
        mock_create_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_lookup_returns_empty_for_invalid_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "bucket",
        )

        videos = await lookup_camera_video_segments(
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
        )

        assert videos == []

    @pytest.mark.asyncio
    async def test_async_lookup_normalizes_times_and_delegates(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker,
    ) -> None:
        monkeypatch.setattr(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "bucket",
        )
        s3_client = MagicMock()
        mocker.patch(
            "services.monitoring_service._video._create_video_s3_client",
            return_value=s3_client,
        )
        mock_to_thread = mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=[],
        )

        videos = await lookup_camera_video_segments(
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5),
            end_time=datetime(2026, 6, 23, 14, 6, tzinfo=timezone.utc),
        )

        assert videos == []
        mock_to_thread.assert_awaited_once()
        call_args = mock_to_thread.await_args
        assert call_args is not None
        assert call_args.args[1] is s3_client
        assert call_args.args[2] == "bucket"
        assert call_args.args[4] == datetime(
            2026,
            6,
            23,
            14,
            5,
            tzinfo=timezone.utc,
        )

    @pytest.mark.asyncio
    async def test_async_lookup_returns_empty_when_lookup_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker,
    ) -> None:
        monkeypatch.setattr(
            "services.monitoring_service._video.AWS_ASSET_BUCKET_NAME",
            "bucket",
        )
        mocker.patch("services.monitoring_service._video._create_video_s3_client")
        mocker.patch(
            "services.monitoring_service._video.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=RuntimeError("s3 failed"),
        )

        videos = await lookup_camera_video_segments(
            video_prefix="security/cameras/account/project/camera/videos/",
            start_time=datetime(2026, 6, 23, 14, 5, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 23, 14, 6, tzinfo=timezone.utc),
        )

        assert videos == []
