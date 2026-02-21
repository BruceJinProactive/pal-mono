"""Video upload implementation for camera recordings.

This module provides streaming upload support for video files,
avoiding memory issues with large video segments.
"""

import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from api.schemas.asset.asset import AssetResponse
from services import signal_source_service
from utils.log import logger

# Get S3 configuration from environment
AWS_ASSET_BUCKET_NAME = os.environ.get("AWS_ASSET_BUCKET_NAME", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Video file size limit (500MB)
MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024

# Supported video extensions and their content types
SUPPORTED_VIDEO_EXTENSIONS: dict[str, str] = {
    ".mkv": "video/x-matroska",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
}


async def upload_camera_video(
    account_id: str,
    project_id: str,
    camera_id: str,
    video: UploadFile,
    session: AsyncSession,
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

    Returns:
        AssetResponse with the S3 key of the uploaded video

    Raises:
        HTTPException: If validation fails or upload errors occur
    """
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

    if file_size > MAX_VIDEO_SIZE_BYTES:
        logger.error(
            "Video file exceeds maximum size",
            extra={
                "video_filename": filename,
                "file_size": file_size,
                "max_size": MAX_VIDEO_SIZE_BYTES,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Video file '{filename}' exceeds maximum size of "
            f"{MAX_VIDEO_SIZE_BYTES // (1024 * 1024)}MB",
        )

    # Build S3 key
    # Format: security/cameras/{account_id}/{project_id}/{camera_id}/videos/{date}/{filename}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s3_key = f"security/cameras/{account_id}/{project_id}/{camera_id}/videos/{today}/{filename}"

    # Upload to S3 using streaming
    try:
        s3_client = boto3.client("s3", region_name=AWS_REGION)

        # Use upload_fileobj for streaming upload (doesn't load entire file into memory)
        # Wrap in run_in_threadpool to avoid blocking the event loop
        await run_in_threadpool(
            s3_client.upload_fileobj,
            video.file,  # SpooledTemporaryFile from FastAPI
            AWS_ASSET_BUCKET_NAME,
            s3_key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {
                    "camera_id": camera_id,
                    "account_id": account_id,
                    "project_id": project_id,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

        logger.info(
            f"Video uploaded successfully: {s3_key}",
            extra={
                "camera_id": camera_id,
                "video_filename": filename,
                "s3_key": s3_key,
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
