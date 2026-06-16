"""Video upload implementation for camera recordings.

This module provides streaming upload support for video files. Videos intended
for LLM analysis keep a stricter size limit because non-MP4 inputs may be
loaded into memory for remuxing before upload.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from api.schemas.asset.asset import AssetResponse
from services import signal_source_service
from services.monitoring_service._video import (
    extract_one_minute_video_frames_from_bytes,
    remux_to_mp4,
)
from utils.log import logger
from utils.vision_capture_time import parse_utc_capture_time_from_path

# Get S3 configuration from environment
AWS_ASSET_BUCKET_NAME = os.environ.get("AWS_ASSET_BUCKET_NAME", "")
AWS_IMAGE_BUCKET_NAME = os.environ.get("AWS_IMAGE_BUCKET_NAME", AWS_ASSET_BUCKET_NAME)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_BYTES_PER_MIB = 1024 * 1024

# Video file size limits. LLM-analysis uploads keep the historical 500MB cap.
# Archive-only uploads are streamed directly to S3 and have no app-level cap by
# default; infra/proxy/S3 limits may still apply.
_DEFAULT_LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES = 500 * _BYTES_PER_MIB


def _read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid positive integer environment value; using default",
            extra={"env_name": name, "env_value": raw_value, "default": default},
        )
        return default

    if value <= 0:
        logger.warning(
            "Non-positive environment value; using default",
            extra={"env_name": name, "env_value": raw_value, "default": default},
        )
        return default

    return value


def _read_optional_max_size_env(name: str) -> int | None:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value == "" or raw_value == "0":
        return None

    try:
        value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid optional max-size environment value; disabling app limit",
            extra={"env_name": name, "env_value": raw_value},
        )
        return None

    if value < 0:
        logger.warning(
            "Negative optional max-size environment value; disabling app limit",
            extra={"env_name": name, "env_value": raw_value},
        )
        return None

    return value


LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES = _read_positive_int_env(
    "CAMERA_VIDEO_ANALYSIS_MAX_SIZE_BYTES",
    _DEFAULT_LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES,
)
ARCHIVE_MAX_VIDEO_SIZE_BYTES = _read_optional_max_size_env(
    "CAMERA_VIDEO_ARCHIVE_MAX_SIZE_BYTES"
)

# Backward-compatible alias for callers/tests that imported the old constant.
MAX_VIDEO_SIZE_BYTES = LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES

# Supported video extensions and their content types
SUPPORTED_VIDEO_EXTENSIONS: dict[str, str] = {
    ".mkv": "video/x-matroska",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
}
ARCHIVE_FRAME_TIMESTAMPS_SECONDS: tuple[float, ...] = (15.0, 30.0, 45.0, 60.0)


def _format_size_limit(max_size_bytes: int) -> str:
    if max_size_bytes % _BYTES_PER_MIB == 0:
        return f"{max_size_bytes // _BYTES_PER_MIB}MB"
    return f"{max_size_bytes} bytes"


def _upload_size_limit(llm_analysis: bool) -> tuple[int | None, str]:
    if llm_analysis:
        return LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES, "LLM analysis"
    return ARCHIVE_MAX_VIDEO_SIZE_BYTES, "archive-only upload"


def _timestamp_suffix(timestamp_seconds: float) -> str:
    return (
        str(int(timestamp_seconds))
        if timestamp_seconds.is_integer()
        else str(timestamp_seconds)
    )


def _frame_capture_time(
    video_filename: str,
    timestamp_seconds: float,
    upload_time: datetime,
) -> datetime:
    video_start = parse_utc_capture_time_from_path(video_filename)
    if video_start is None:
        video_start = upload_time
    return video_start + timedelta(seconds=timestamp_seconds)


def _archive_frame_s3_key(
    account_id: str,
    project_id: str,
    camera_id: str,
    video_filename: str,
    timestamp_seconds: float,
    upload_time: datetime,
) -> str:
    captured_at = _frame_capture_time(video_filename, timestamp_seconds, upload_time)
    capture_date = captured_at.strftime("%Y-%m-%d")
    frame_filename = f"{captured_at.strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
    return (
        f"security/cameras/{account_id}/{project_id}/{camera_id}"
        f"/images/{capture_date}/{frame_filename}"
    )


async def _log_archive_frame_retrieval_status(
    s3_client: Any,
    bucket_name: str,
    frame_key: str,
    camera_id: str,
    video_s3_key: str,
    timestamp_seconds: float,
) -> None:
    try:
        response = await run_in_threadpool(
            s3_client.head_object,
            Bucket=bucket_name,
            Key=frame_key,
        )
        logger.info(
            "Archive frame uploaded and verified retrievable",
            extra={
                "camera_id": camera_id,
                "bucket": bucket_name,
                "frame_s3_key": frame_key,
                "source_video_key": video_s3_key,
                "timestamp_seconds": timestamp_seconds,
                "content_length": response.get("ContentLength"),
            },
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning(
            "Archive frame uploaded but retrieval verification failed",
            extra={
                "camera_id": camera_id,
                "bucket": bucket_name,
                "frame_s3_key": frame_key,
                "source_video_key": video_s3_key,
                "timestamp_seconds": timestamp_seconds,
                "error_code": error_code,
                "error": str(e),
            },
        )
    except Exception as e:
        logger.warning(
            "Archive frame uploaded but retrieval verification failed",
            extra={
                "camera_id": camera_id,
                "bucket": bucket_name,
                "frame_s3_key": frame_key,
                "source_video_key": video_s3_key,
                "timestamp_seconds": timestamp_seconds,
                "error": str(e),
            },
        )


async def _upload_archive_frames(
    s3_client: Any,
    account_id: str,
    project_id: str,
    camera_id: str,
    video_filename: str,
    video_s3_key: str,
    frames: list[dict[str, Any]],
    upload_time: datetime,
) -> list[str]:
    frame_s3_keys: list[str] = []
    for frame in frames:
        timestamp_seconds = float(frame["timestamp_seconds"])
        source_timestamp_seconds = float(
            frame.get("source_timestamp_seconds", timestamp_seconds)
        )
        frame_key = _archive_frame_s3_key(
            account_id=account_id,
            project_id=project_id,
            camera_id=camera_id,
            video_filename=video_filename,
            timestamp_seconds=source_timestamp_seconds,
            upload_time=upload_time,
        )
        await run_in_threadpool(
            s3_client.upload_fileobj,
            BytesIO(frame["jpeg_bytes"]),
            AWS_IMAGE_BUCKET_NAME,
            frame_key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "Metadata": {
                    "camera_id": camera_id,
                    "account_id": account_id,
                    "project_id": project_id,
                    "source_video_key": video_s3_key,
                    "timestamp_seconds": _timestamp_suffix(timestamp_seconds),
                    "source_timestamp_seconds": _timestamp_suffix(
                        source_timestamp_seconds
                    ),
                },
            },
        )
        await _log_archive_frame_retrieval_status(
            s3_client=s3_client,
            bucket_name=AWS_IMAGE_BUCKET_NAME,
            frame_key=frame_key,
            camera_id=camera_id,
            video_s3_key=video_s3_key,
            timestamp_seconds=timestamp_seconds,
        )
        frame_s3_keys.append(frame_key)

    return frame_s3_keys


async def upload_camera_video(
    account_id: str,
    project_id: str,
    camera_id: str,
    video: UploadFile,
    session: AsyncSession,
    llm_analysis: bool = True,
) -> AssetResponse:
    """
    Upload a video segment from a camera to S3 using streaming.

    This function streams the video file directly to S3 without loading
    the entire file into memory, making it suitable for large video files.

    Args:
        account_id: The account UUID
        project_id: The project UUID
        camera_id: The camera identifier
        video: The video file to upload
        session: Database session for camera validation
        llm_analysis: Whether the uploaded video is intended for LLM analysis.
            Stored as S3 object metadata.

    Returns:
        AssetResponse with the S3 key of the uploaded video

    Raises:
        HTTPException: If validation fails or upload errors occur
    """
    if not llm_analysis and not AWS_IMAGE_BUCKET_NAME:
        logger.error("AWS_IMAGE_BUCKET_NAME not configured for archive frame upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image storage not configured",
        )

    # Validate camera exists (optional - log warning but don't block)
    try:
        source = await signal_source_service.get_source_by_camera_id(
            session=session,
            project_id=uuid.UUID(project_id),
            camera_id=camera_id,
        )
        if not source:
            logger.warning(
                "Camera not found for video upload",
                extra={
                    "camera_id": camera_id,
                    "project_id": project_id,
                    "account_id": account_id,
                },
            )
    except Exception as e:
        logger.error(
            "Failed to lookup camera for video upload",
            extra={
                "camera_id": camera_id,
                "project_id": project_id,
                "account_id": account_id,
                "error": str(e),
            },
        )

    # Validate filename is provided
    if not video.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video filename is required",
        )

    # Normalize filename to prevent path traversal attacks
    filename = os.path.basename(video.filename)
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video filename",
        )

    # Validate file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_VIDEO_EXTENSIONS:
        logger.error(
            "Unsupported video file extension",
            extra={
                "video_filename": filename,
                "extension": ext,
                "supported_extensions": list(SUPPORTED_VIDEO_EXTENSIONS.keys()),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video file extension '{ext}' for file '{filename}'. "
            f"Supported extensions: {', '.join(SUPPORTED_VIDEO_EXTENSIONS.keys())}",
        )

    content_type = SUPPORTED_VIDEO_EXTENSIONS[ext]

    # Check file size
    # First try video.size (set by FastAPI if Content-Length header present)
    file_size = video.size
    if file_size is None:
        # Fall back to seeking to end of file to determine size
        current_pos = video.file.tell()
        video.file.seek(0, 2)  # Seek to end
        file_size = video.file.tell()
        video.file.seek(current_pos)  # Seek back to original position

    max_size_bytes, size_limit_context = _upload_size_limit(llm_analysis)
    if max_size_bytes is not None and file_size > max_size_bytes:
        logger.error(
            "Video file exceeds maximum size",
            extra={
                "video_filename": filename,
                "file_size": file_size,
                "max_size": max_size_bytes,
                "llm_analysis": llm_analysis,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Video file '{filename}' exceeds maximum size of "
            f"{_format_size_limit(max_size_bytes)} for {size_limit_context}",
        )

    upload_file = video.file
    archive_frames: list[dict[str, Any]] = []
    archive_video_duration_seconds: float | None = None

    if not llm_analysis:
        try:
            video_bytes = await run_in_threadpool(video.file.read)
            archive_video_duration_seconds, archive_frames = await run_in_threadpool(
                extract_one_minute_video_frames_from_bytes,
                video_bytes,
                ARCHIVE_FRAME_TIMESTAMPS_SECONDS,
            )
            upload_file = BytesIO(video_bytes)
        except ValueError as e:
            logger.error(
                "Archive-only video failed duration/frame validation",
                extra={
                    "camera_id": camera_id,
                    "video_filename": filename,
                    "error": str(e),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

    # Remux non-MP4 containers (e.g. MKV) to MP4 only when the video is meant
    # for LLM analysis. Archive-only uploads keep the original file after
    # one-minute validation and frame extraction above.
    elif ext in {".mkv", ".avi", ".webm"}:
        try:
            video_bytes = await run_in_threadpool(video.file.read)
            if not video_bytes:
                logger.warning(
                    f"Skipping remux for empty {ext} upload; uploading original",
                    extra={
                        "camera_id": camera_id,
                        "video_filename": filename,
                    },
                )
                video.file.seek(0)
                upload_file = video.file
            else:
                mp4_bytes = await run_in_threadpool(remux_to_mp4, video_bytes)

                # Validate remuxed size (re-encoding can inflate the output)
                if len(mp4_bytes) > LLM_ANALYSIS_MAX_VIDEO_SIZE_BYTES:
                    logger.warning(
                        f"Remuxed MP4 exceeds size limit ({len(mp4_bytes)} bytes), uploading original",
                        extra={
                            "camera_id": camera_id,
                            "original_size": len(video_bytes),
                            "mp4_size": len(mp4_bytes),
                        },
                    )
                    video.file.seek(0)
                    upload_file = video.file
                else:
                    upload_file = BytesIO(mp4_bytes)
                    filename = os.path.splitext(filename)[0] + ".mp4"
                    content_type = "video/mp4"
                    logger.info(
                        f"Remuxed {ext} to MP4 for upload",
                        extra={
                            "camera_id": camera_id,
                            "original_ext": ext,
                            "original_size": len(video_bytes),
                            "mp4_size": len(mp4_bytes),
                        },
                    )
        except Exception as e:
            logger.error(
                f"Failed to remux {ext} to MP4, uploading original: {e}",
                extra={
                    "camera_id": camera_id,
                    "video_filename": filename,
                    "error": str(e),
                },
            )
            # Reset file position and upload original on remux failure
            video.file.seek(0)
            upload_file = video.file

    # Build S3 key
    # Format: security/cameras/{account_id}/{project_id}/{camera_id}/videos/{date}/{filename}
    uploaded_at = datetime.now(timezone.utc)
    today = uploaded_at.strftime("%Y-%m-%d")
    s3_key = f"security/cameras/{account_id}/{project_id}/{camera_id}/videos/{today}/{filename}"

    # Upload to S3 using streaming
    try:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        archive_frame_s3_keys: list[str] = []
        if archive_frames:
            archive_frame_s3_keys = await _upload_archive_frames(
                s3_client=s3_client,
                account_id=account_id,
                project_id=project_id,
                camera_id=camera_id,
                video_filename=filename,
                video_s3_key=s3_key,
                frames=archive_frames,
                upload_time=uploaded_at,
            )

        # Use upload_fileobj for streaming upload (doesn't load entire file into memory)
        # Wrap in run_in_threadpool to avoid blocking the event loop
        metadata = {
            "camera_id": camera_id,
            "account_id": account_id,
            "project_id": project_id,
            "llm_analysis": str(llm_analysis).lower(),
            "uploaded_at": uploaded_at.isoformat(),
        }
        if archive_frame_s3_keys:
            metadata.update(
                {
                    "archive_frame_s3_keys": ",".join(archive_frame_s3_keys),
                    "archive_frame_timestamps_seconds": ",".join(
                        _timestamp_suffix(timestamp)
                        for timestamp in ARCHIVE_FRAME_TIMESTAMPS_SECONDS
                    ),
                    "archive_video_duration_seconds": (
                        f"{archive_video_duration_seconds:.3f}"
                        if archive_video_duration_seconds is not None
                        else ""
                    ),
                }
            )

        await run_in_threadpool(
            s3_client.upload_fileobj,
            upload_file,
            AWS_ASSET_BUCKET_NAME,
            s3_key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": metadata,
            },
        )

        logger.info(
            f"Video uploaded successfully: {s3_key}",
            extra={
                "camera_id": camera_id,
                "video_filename": filename,
                "s3_key": s3_key,
                "llm_analysis": llm_analysis,
            },
        )

        # Return the S3 key (not presigned URL - consistent with image upload)
        return AssetResponse(url=s3_key)

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error(
            f"S3 upload failed: {error_code}",
            extra={
                "camera_id": camera_id,
                "video_filename": filename,
                "s3_key": s3_key,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video to S3: {error_code}",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during video upload: {e}",
            extra={
                "camera_id": camera_id,
                "video_filename": filename,
                "s3_key": s3_key,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during video upload",
        )
