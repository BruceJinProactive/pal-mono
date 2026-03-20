"""Tests for audio recording upload endpoint."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, UploadFile


class TestUploadRecording:
    """Tests for upload_recording endpoint."""

    @pytest.mark.asyncio
    async def test_happy_path_ogg_upload(self, mocker):
        """Should upload OGG file successfully and return S3 URI."""
        from api.routes.internal._voice import upload_recording

        audio_bytes = b"fake-ogg-audio-data"
        audio_file = BytesIO(audio_bytes)
        upload = UploadFile(
            filename="recording.ogg",
            file=audio_file,
        )

        mock_s3 = MagicMock()
        mocker.patch(
            "services.asset_service._utils.init_s3",
            return_value=mock_s3,
        )
        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-audio-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        result = await upload_recording(upload, "call-123", "room-abc")

        assert result == {
            "audio_recording_s3_uri": "s3://test-audio-bucket/recordings/room-abc/call-123.ogg"
        }
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args[1]
        assert call_args["Bucket"] == "test-audio-bucket"
        assert call_args["Key"] == "recordings/room-abc/call-123.ogg"
        assert call_args["Body"] == audio_bytes

    @pytest.mark.asyncio
    async def test_correct_s3_key_format(self, mocker):
        """Should use correct S3 key pattern: recordings/{room_name}/{call_id}.ext"""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"audio-data")
        upload = UploadFile(filename="rec.wav", file=audio_file)

        mock_s3 = MagicMock()
        mocker.patch(
            "services.asset_service._utils.init_s3",
            return_value=mock_s3,
        )
        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-west-2",
            },
        )

        result = await upload_recording(upload, "call-456", "test-room")

        assert "recordings/test-room/call-456.wav" in result["audio_recording_s3_uri"]
        call_args = mock_s3.put_object.call_args[1]
        assert call_args["Key"] == "recordings/test-room/call-456.wav"

    @pytest.mark.asyncio
    async def test_empty_file_returns_400(self, mocker):
        """Should reject empty files with 400 status."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"")
        upload = UploadFile(filename="empty.ogg", file=audio_file)

        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_recording(upload, "call-123", "room-abc")

        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_file_too_large_returns_413(self, mocker):
        """Should reject files >10MB with 413 status."""
        from api.routes.internal._voice import upload_recording

        # Create file larger than 10MB
        large_audio = b"x" * (11 * 1024 * 1024)
        audio_file = BytesIO(large_audio)
        upload = UploadFile(filename="large.ogg", file=audio_file)

        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_recording(upload, "call-123", "room-abc")

        assert exc_info.value.status_code == 413
        assert "exceeds maximum" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unsupported_extension_returns_400(self, mocker):
        """Should reject files with unsupported extensions."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"not-audio-data")
        upload = UploadFile(filename="recording.txt", file=audio_file)

        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_recording(upload, "call-123", "room-abc")

        assert exc_info.value.status_code == 400
        assert "unsupported" in exc_info.value.detail.lower()
        assert ".txt" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_s3_upload_failure_returns_500(self, mocker):
        """Should return 500 when S3 upload fails."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"audio-data")
        upload = UploadFile(filename="recording.ogg", file=audio_file)

        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 connection failed")

        mocker.patch(
            "services.asset_service._utils.init_s3",
            return_value=mock_s3,
        )
        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_recording(upload, "call-123", "room-abc")

        assert exc_info.value.status_code == 500
        assert "Failed to upload to S3" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wav_file_accepted(self, mocker):
        """Should accept WAV files."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"wav-data")
        upload = UploadFile(filename="recording.wav", file=audio_file)

        mock_s3 = MagicMock()
        mocker.patch(
            "services.asset_service._utils.init_s3",
            return_value=mock_s3,
        )
        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        result = await upload_recording(upload, "call-123", "room-abc")

        assert result["audio_recording_s3_uri"].endswith(".wav")

    @pytest.mark.asyncio
    async def test_mp3_file_accepted(self, mocker):
        """Should accept MP3 files."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"mp3-data")
        upload = UploadFile(filename="recording.mp3", file=audio_file)

        mock_s3 = MagicMock()
        mocker.patch(
            "services.asset_service._utils.init_s3",
            return_value=mock_s3,
        )
        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        result = await upload_recording(upload, "call-123", "room-abc")

        assert result["audio_recording_s3_uri"].endswith(".mp3")

    @pytest.mark.asyncio
    async def test_missing_bucket_config_returns_500(self, mocker):
        """Should return 500 if AUDIO_RECORDINGS_S3_BUCKET is not configured."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"audio-data")
        upload = UploadFile(filename="recording.ogg", file=audio_file)

        mocker.patch.dict("os.environ", {}, clear=True)

        with pytest.raises(HTTPException) as exc_info:
            await upload_recording(upload, "call-123", "room-abc")

        assert exc_info.value.status_code == 500
        assert "bucket not configured" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_filename_returns_400(self, mocker):
        """Should reject uploads with no filename."""
        from api.routes.internal._voice import upload_recording

        audio_file = BytesIO(b"audio-data")
        upload = UploadFile(filename=None, file=audio_file)

        mocker.patch.dict(
            "os.environ",
            {
                "AUDIO_RECORDINGS_S3_BUCKET": "test-bucket",
                "AWS_REGION": "us-east-1",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_recording(upload, "call-123", "room-abc")

        assert exc_info.value.status_code == 400
        assert "filename" in exc_info.value.detail.lower()
