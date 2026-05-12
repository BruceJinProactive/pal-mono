"""Photo upload implementation for camera snapshots.

Handles JPEG uploads from camera snapshot systems, storing them in the
dedicated images S3 bucket and updating the signal feed's last_capture
timestamp to keep the "camera alive" indicator working.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from api.schemas.asset.asset import AssetResponse
from db.repositories import SignalFeedRepositoryAsync
from services import signal_source_service
from utils.log import logger

# S3 configuration — uses the same asset bucket as video uploads
AWS_IMAGE_BUCKET_NAME = os.environ.get(
    "AWS_IMAGE_BUCKET_NAME", os.environ.get("AWS_ASSET_BUCKET_NAME", "")
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Photo file size limit (10MB — JPEG snapshots are typically <500KB)
MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024

# Supported image extensions
SUPPORTED_PHOTO_EXTENSIONS: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


async def upload_camera_photo(
    account_id: str,
    project_id: str,
    camera_id: str,
    photo: UploadFile,
    session: AsyncSession,
) -> AssetResponse:
    """Upload a photo snapshot from a camera to S3.

    Stores the image in the dedicated images bucket and updates the
    signal feed's last_capture_at/last_capture_url to signal liveness.

    Args:
        account_id: The account UUID.
        project_id: The project UUID.
        camera_id: The camera identifier.
        photo: The image file to upload.
        session: Database session for camera validation and feed update.

    Returns:
        AssetResponse with the S3 key of the uploaded photo.

    Raises:
        HTTPException: If validation fails or upload errors occur.
    """
    if not AWS_IMAGE_BUCKET_NAME:
        logger.error("AWS_IMAGE_BUCKET_NAME not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image storage not configured",
        )

    # Validate camera exists (warn but don't block)
    source = None
    try:
        source = await signal_source_service.get_source_by_camera_id(
            session=session,
            project_id=uuid.UUID(project_id),
            camera_id=camera_id,
        )
        if not source:
            logger.warning(
                "Camera not found for photo upload",
                extra={
                    "camera_id": camera_id,
                    "project_id": project_id,
                    "account_id": account_id,
                },
            )
    except Exception as e:
        logger.error(
            "Failed to lookup camera for photo upload",
            extra={
                "camera_id": camera_id,
                "project_id": project_id,
                "error": str(e),
            },
        )

    # Validate filename
    if not photo.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Photo filename is required",
        )

    filename = os.path.basename(photo.filename)
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid photo filename",
        )

    # Validate extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_PHOTO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported photo extension '{ext}'. "
            f"Supported: {', '.join(SUPPORTED_PHOTO_EXTENSIONS.keys())}",
        )

    content_type = SUPPORTED_PHOTO_EXTENSIONS[ext]

    # Check file size
    file_size = photo.size
    if file_size is None:
        current_pos = photo.file.tell()
        photo.file.seek(0, 2)
        file_size = photo.file.tell()
        photo.file.seek(current_pos)

    if file_size > MAX_PHOTO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Photo exceeds maximum size of "
            f"{MAX_PHOTO_SIZE_BYTES // (1024 * 1024)}MB",
        )

    # Build S3 key (include short UUID suffix to prevent same-second collisions)
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    # Use human-readable camera name in path when available, fall back to camera_id
    camera_folder = source.name if source and source.name else camera_id
    s3_key = (
        f"security/cameras/{account_id}/{project_id}/{camera_folder}"
        f"/images/{today}/{timestamp}-{suffix}{ext}"
    )

    # Upload to S3
    try:
        s3_client = boto3.client("s3", region_name=AWS_REGION)

        # Reset file pointer to ensure full content is uploaded
        photo.file.seek(0)

        await run_in_threadpool(
            s3_client.upload_fileobj,
            photo.file,
            AWS_IMAGE_BUCKET_NAME,
            s3_key,
            ExtraArgs={
                "ContentType": content_type,
                "Metadata": {
                    "camera_id": camera_id,
                    "account_id": account_id,
                    "project_id": project_id,
                    "captured_at": now.isoformat(),
                },
            },
        )

        logger.info(
            "Photo uploaded successfully",
            extra={
                "camera_id": camera_id,
                "s3_key": s3_key,
                "bucket": AWS_IMAGE_BUCKET_NAME,
            },
        )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error(
            f"S3 photo upload failed: {error_code}",
            extra={
                "camera_id": camera_id,
                "s3_key": s3_key,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload photo to S3: {error_code}",
        )
    except Exception as e:
        logger.error(
            "Unexpected error during photo upload",
            extra={
                "camera_id": camera_id,
                "s3_key": s3_key,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during photo upload",
        )

    # Update signal feed last_capture (best-effort, don't fail the upload)
    if source:
        try:
            feed_repo = SignalFeedRepositoryAsync(session)
            feed = await feed_repo.get_by_source_id(source.id)
            if feed:
                await feed_repo.update_last_capture(feed.id, now, s3_key)
                await session.commit()
        except Exception as e:
            logger.warning(
                "Failed to update signal feed after photo upload",
                extra={
                    "camera_id": camera_id,
                    "source_id": str(source.id),
                    "error": str(e),
                },
            )

    return AssetResponse(url=s3_key)
