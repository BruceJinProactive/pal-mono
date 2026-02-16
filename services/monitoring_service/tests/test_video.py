"""Tests for video frame extraction logic."""

import base64
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.monitoring_service._video import (
    _extract_frames_sync,
    extract_video_frames,
)


class TestExtractFramesSync:
    """Tests for _extract_frames_sync — synchronous frame extraction."""

    def test_extracts_frames_at_intervals(self, mocker):
        """Should extract frames at the configured interval from the video."""
        # Create a mock frame that can be converted to image
        mock_pil_image = MagicMock()
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
        )

        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 30
        mock_stream.time_base = 1  # 1 second per unit
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        # Return a fresh iterator each time decode is called
        mock_container.decode.side_effect = lambda **kwargs: iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)

        # Should have frames at 0, 10, 20 seconds (30s duration, 10s interval)
        assert len(frames) == 3

    def test_always_includes_frame_at_zero(self, mocker):
        """Should always include a frame at t=0."""
        mock_pil_image = MagicMock()
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 5
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.decode.return_value = iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)
        assert len(frames) >= 1
        assert frames[0]["timestamp_seconds"] == 0.0

    def test_generates_correct_timestamp_labels(self, mocker):
        """Should generate timestamp labels in M:SS format."""
        mock_pil_image = MagicMock()
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 70
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.decode.side_effect = lambda **kwargs: iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=30)

        # Frames at 0, 30, 60 seconds
        assert frames[0]["timestamp_label"] == "0:00"
        assert frames[1]["timestamp_label"] == "0:30"
        assert frames[2]["timestamp_label"] == "1:00"

    def test_returns_base64_data(self, mocker):
        """Should return base64-encoded JPEG data for each frame."""
        mock_pil_image = MagicMock()
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
        )
        mock_frame = MagicMock()
        mock_frame.to_image.return_value = mock_pil_image

        mock_stream = MagicMock()
        mock_stream.duration = 5
        mock_stream.time_base = 1
        mock_stream.average_rate = 30

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.decode.return_value = iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        frames = _extract_frames_sync("/fake/video.mp4")
        assert len(frames) >= 1
        # Verify the base64 data can be decoded
        decoded = base64.b64decode(frames[0]["base64_data"])
        assert decoded == b"fake-jpeg-data"

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
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
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
        mock_container.decode.return_value = iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        frames = _extract_frames_sync("/fake/video.mp4")
        assert len(frames) == 1
        assert frames[0]["timestamp_seconds"] == 0.0

    def test_falls_back_to_container_duration(self, mocker):
        """Should use container.duration when stream.duration is None."""
        mock_pil_image = MagicMock()
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
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
        mock_container.decode.side_effect = lambda **kwargs: iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
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
        mock_pil_image.save = MagicMock(
            side_effect=lambda buf, **kwargs: buf.write(b"fake-jpeg-data")
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
        mock_container.decode.return_value = iter([mock_frame])

        mocker.patch(
            "services.monitoring_service._video.av.open",
            return_value=mock_container,
        )

        frames = _extract_frames_sync("/fake/video.mp4", frame_interval_seconds=10)
        assert len(frames) == 1
        assert frames[0]["timestamp_seconds"] == 0.0


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
