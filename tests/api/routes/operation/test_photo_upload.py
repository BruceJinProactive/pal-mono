"""Tests for camera photo upload endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile


def _make_upload(
    filename: str = "snapshot.jpg", content: bytes = b"fake-jpeg"
) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content), size=len(content))


def _setup_mocks(mocker) -> tuple[MagicMock, MagicMock, AsyncMock]:
    """Set up common mocks. Returns (s3_mock, source_mock, feed_repo_mock)."""
    s3_mock = MagicMock()
    mocker.patch(
        "api.routes.operation._photo_upload.boto3.client",
        return_value=s3_mock,
    )

    source = MagicMock()
    source.id = "source-id-123"
    source.name = "front-door-cam"
    mocker.patch(
        "api.routes.operation._photo_upload.signal_source_service.get_source_by_camera_id",
        new_callable=AsyncMock,
        return_value=source,
    )

    feed = MagicMock()
    feed.id = "feed-id-456"
    repo_instance = AsyncMock()
    repo_instance.get_by_source_id = AsyncMock(return_value=feed)
    repo_instance.update_last_capture = AsyncMock(return_value=feed)
    mocker.patch(
        "api.routes.operation._photo_upload.SignalFeedRepositoryAsync",
        return_value=repo_instance,
    )

    return s3_mock, source, repo_instance


class TestUploadCameraPhoto:
    @pytest.mark.asyncio
    async def test_successful_upload(self, mocker) -> None:
        """Should upload JPEG to S3 and return S3 key."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock, _, _ = _setup_mocks(mocker)
        session = AsyncMock()
        upload = _make_upload()

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        assert result.url.startswith(
            "security/cameras/00000000-0000-0000-0000-000000000001/00000000-0000-0000-0000-000000000002/front-door-cam/images/"
        )
        assert result.url.endswith(".jpg")
        s3_mock.upload_fileobj.assert_called_once()
        call_args = s3_mock.upload_fileobj.call_args
        assert call_args[0][1] == "test-images-bucket"
        assert call_args[1]["ExtraArgs"]["ContentType"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_timestamp_filename_uses_capture_time_key(self, mocker) -> None:
        """Should preserve UTC capture timestamp filenames in the S3 key."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock, _, feed_repo = _setup_mocks(mocker)
        session = AsyncMock()
        upload = _make_upload(filename="snapshots/2026-06-09/2026-06-09_18-51-35.jpg")

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        assert result.url == (
            "security/cameras/00000000-0000-0000-0000-000000000001/"
            "00000000-0000-0000-0000-000000000002/front-door-cam/"
            "images/2026-06-09/2026-06-09_18-51-35.jpg"
        )
        call_args = s3_mock.upload_fileobj.call_args
        assert call_args[0][2] == result.url
        assert call_args[1]["ExtraArgs"]["Metadata"]["captured_at"] == (
            "2026-06-09T18:51:35+00:00"
        )
        feed_repo.update_last_capture.assert_called_once_with(
            "feed-id-456",
            datetime(2026, 6, 9, 18, 51, 35, tzinfo=timezone.utc),
            result.url,
        )

    @pytest.mark.asyncio
    async def test_non_timestamp_filename_warns_and_uses_fallback_key(
        self, mocker
    ) -> None:
        """Should warn and preserve old generated filename behavior."""
        from api.routes.operation._photo_upload import upload_camera_photo

        warning_mock = mocker.patch("api.routes.operation._photo_upload.logger.warning")
        s3_mock, _, _ = _setup_mocks(mocker)
        session = AsyncMock()
        upload = _make_upload(filename="snapshot.jpg")

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        assert result.url.endswith(".jpg")
        assert not result.url.endswith("/snapshot.jpg")
        s3_mock.upload_fileobj.assert_called_once()
        warning_mock.assert_any_call(
            "Camera snapshot filename does not include UTC capture timestamp; "
            "falling back to upload time",
            extra={
                "camera_id": "cam-1",
                "project_id": "00000000-0000-0000-0000-000000000002",
                "account_id": "00000000-0000-0000-0000-000000000001",
                "snapshot_filename": "snapshot.jpg",
                "expected_format": "snapshots/YYYY-MM-DD/YYYY-MM-DD_HH-MM-SS.jpg",
            },
        )

    @pytest.mark.asyncio
    async def test_updates_signal_feed(self, mocker) -> None:
        """Should update signal feed last_capture after upload."""
        from api.routes.operation._photo_upload import upload_camera_photo

        _, _, feed_repo = _setup_mocks(mocker)
        session = AsyncMock()
        upload = _make_upload()

        await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        feed_repo.get_by_source_id.assert_called_once()
        feed_repo.update_last_capture.assert_called_once()
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_png_extension_accepted(self, mocker) -> None:
        """Should accept PNG files."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock, _, _ = _setup_mocks(mocker)
        session = AsyncMock()
        upload = _make_upload(filename="frame.png")

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        assert result.url.endswith(".png")
        call_args = s3_mock.upload_fileobj.call_args
        assert call_args[1]["ExtraArgs"]["ContentType"] == "image/png"

    @pytest.mark.asyncio
    async def test_unsupported_extension_rejected(self, mocker) -> None:
        """Should reject unsupported file extensions."""
        from api.routes.operation._photo_upload import upload_camera_photo

        _setup_mocks(mocker)
        session = AsyncMock()
        upload = _make_upload(filename="photo.gif")

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_photo(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "cam-1",
                upload,
                session,
            )

        assert exc_info.value.status_code == 400
        assert "Unsupported" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_filename_rejected(self, mocker) -> None:
        """Should reject upload with no filename."""
        from api.routes.operation._photo_upload import upload_camera_photo

        _setup_mocks(mocker)
        session = AsyncMock()
        upload = UploadFile(filename="", file=BytesIO(b"data"), size=4)

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_photo(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "cam-1",
                upload,
                session,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self, mocker) -> None:
        """Should reject files over 10MB."""
        from api.routes.operation._photo_upload import upload_camera_photo

        _setup_mocks(mocker)
        session = AsyncMock()
        big_content = b"x" * (11 * 1024 * 1024)
        upload = _make_upload(content=big_content)

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_photo(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "cam-1",
                upload,
                session,
            )

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_bucket_not_configured(self, mocker) -> None:
        """Should return 500 when bucket env var is empty."""
        from api.routes.operation._photo_upload import upload_camera_photo

        mocker.patch("api.routes.operation._photo_upload.AWS_IMAGE_BUCKET_NAME", "")
        session = AsyncMock()
        upload = _make_upload()

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_photo(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "cam-1",
                upload,
                session,
            )

        assert exc_info.value.status_code == 500
        assert "not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_s3_client_error_raises_500(self, mocker) -> None:
        """Should raise 500 on S3 ClientError."""
        from botocore.exceptions import ClientError

        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock, _, _ = _setup_mocks(mocker)
        s3_mock.upload_fileobj.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "PutObject",
        )
        session = AsyncMock()
        upload = _make_upload()

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_photo(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "cam-1",
                upload,
                session,
            )

        assert exc_info.value.status_code == 500
        assert "AccessDenied" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unexpected_s3_error_raises_500(self, mocker) -> None:
        """Should raise 500 on unexpected S3 errors."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock, _, _ = _setup_mocks(mocker)
        s3_mock.upload_fileobj.side_effect = RuntimeError("network down")
        session = AsyncMock()
        upload = _make_upload()

        with pytest.raises(HTTPException) as exc_info:
            await upload_camera_photo(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "cam-1",
                upload,
                session,
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_camera_not_found_still_uploads(self, mocker) -> None:
        """Should proceed with upload even when camera not found."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock = MagicMock()
        mocker.patch(
            "api.routes.operation._photo_upload.boto3.client",
            return_value=s3_mock,
        )
        mocker.patch(
            "api.routes.operation._photo_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=None,
        )
        session = AsyncMock()
        upload = _make_upload()

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        assert result.url.startswith("security/cameras/")
        s3_mock.upload_fileobj.assert_called_once()

    @pytest.mark.asyncio
    async def test_camera_lookup_error_still_uploads(self, mocker) -> None:
        """Should proceed with upload even when camera lookup raises."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock = MagicMock()
        mocker.patch(
            "api.routes.operation._photo_upload.boto3.client",
            return_value=s3_mock,
        )
        mocker.patch(
            "api.routes.operation._photo_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db error"),
        )
        session = AsyncMock()
        upload = _make_upload()

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        assert result.url.startswith("security/cameras/")

    @pytest.mark.asyncio
    async def test_feed_update_failure_doesnt_fail_upload(self, mocker) -> None:
        """Should return success even if feed update fails."""
        from api.routes.operation._photo_upload import upload_camera_photo

        s3_mock = MagicMock()
        mocker.patch(
            "api.routes.operation._photo_upload.boto3.client",
            return_value=s3_mock,
        )
        source = MagicMock()
        source.id = "source-id-123"
        source.name = "front-door-cam"
        mocker.patch(
            "api.routes.operation._photo_upload.signal_source_service.get_source_by_camera_id",
            new_callable=AsyncMock,
            return_value=source,
        )
        repo_instance = AsyncMock()
        repo_instance.get_by_source_id = AsyncMock(side_effect=RuntimeError("db error"))
        mocker.patch(
            "api.routes.operation._photo_upload.SignalFeedRepositoryAsync",
            return_value=repo_instance,
        )
        session = AsyncMock()
        upload = _make_upload()

        result = await upload_camera_photo(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "cam-1",
            upload,
            session,
        )

        # Upload succeeded despite feed update failure
        assert result.url.startswith("security/cameras/")
