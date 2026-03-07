"""Monitoring Service Video Frame Extraction.

Downloads video files from S3 and extracts frames at regular intervals
using PyAV for use in VLM-based monitoring analysis.
"""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from io import BytesIO

import av
import boto3
from fastapi import HTTPException, status

from utils.log import logger

# AWS Configuration (reuse same env vars as _llm.py)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")


def _extract_frames_sync(
    video_path: str, frame_interval_seconds: int = 10
) -> list[dict]:
    """
    Extract frames from a video file at regular intervals.

    Opens the video with PyAV, seeks to each interval mark, and decodes
    one frame per interval. Each frame is encoded as a base64 JPEG string.

    Args:
        video_path: Local file path to the video file
        frame_interval_seconds: Interval in seconds between extracted frames (default: 10)

    Returns:
        List of dicts with keys:
            - base64_data: Base64-encoded JPEG image data
            - timestamp_seconds: Frame timestamp in seconds
            - timestamp_label: Human-readable timestamp (e.g., "0:00:10")
    """
    frames: list[dict] = []

    container = av.open(video_path)
    try:
        stream = container.streams.video[0]

        # Try stream-level duration first, fall back to container-level duration.
        # Some video formats (e.g., certain MP4, WebM) don't set duration on the
        # stream, only on the container (in microseconds / AV_TIME_BASE).
        if stream.duration and stream.time_base:
            duration_seconds = float(stream.duration * stream.time_base)
        elif container.duration:
            duration_seconds = container.duration / 1_000_000.0
        else:
            duration_seconds = 0.0
        fps = float(stream.average_rate) if stream.average_rate else 30.0

        logger.info(
            f"[Video Extraction] Video info - Duration: {duration_seconds:.1f}s, "
            f"FPS: {fps:.1f}, Interval: {frame_interval_seconds}s"
        )

        # Always extract frame at 0s, then at each interval
        timestamps = [0.0]
        if duration_seconds > 0:
            t = float(frame_interval_seconds)
            while t < duration_seconds:
                timestamps.append(t)
                t += frame_interval_seconds

        for target_ts in timestamps:
            try:
                # Seek to target timestamp
                time_base = stream.time_base or 1
                target_pts = int(target_ts / time_base)
                container.seek(target_pts, stream=stream)

                # Decode the next frame after seeking
                for frame in container.decode(video=0):
                    # Convert frame to PIL Image, then to JPEG bytes
                    pil_image = frame.to_image()
                    buffer = BytesIO()
                    pil_image.save(buffer, format="JPEG", quality=85)
                    jpeg_bytes = buffer.getvalue()

                    # Format timestamp label
                    minutes = int(target_ts) // 60
                    seconds = int(target_ts) % 60
                    timestamp_label = f"{minutes}:{seconds:02d}"

                    frames.append(
                        {
                            "base64_data": base64.b64encode(jpeg_bytes).decode("utf-8"),
                            "timestamp_seconds": target_ts,
                            "timestamp_label": timestamp_label,
                        }
                    )
                    break  # Only need one frame per timestamp

            except Exception as e:
                logger.warning(
                    f"[Video Extraction] Failed to extract frame at {target_ts}s: {e}"
                )
                continue

    finally:
        container.close()

    logger.info(f"[Video Extraction] Extracted {len(frames)} frames from video")
    return frames


async def download_video_bytes(video_s3_key: str) -> tuple[bytes, str]:
    """
    Download a video from S3 and return the raw bytes.

    Used for native video analysis where the entire video is passed
    directly to the LLM instead of extracting frames.

    Args:
        video_s3_key: S3 key of the video file

    Returns:
        Tuple of (video_bytes, mime_type)

    Raises:
        HTTPException 500: If video download fails
    """
    s3_client = (
        boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("LOCAL_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("LOCAL_AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("LOCAL_AWS_SESSION_TOKEN"),
        )
        if os.getenv("LOCAL_AWS_ACCESS_KEY_ID")
        else boto3.client("s3", region_name=AWS_REGION)
    )

    try:
        logger.info(f"[Video Download] Downloading video from S3: {video_s3_key}")
        response = await asyncio.to_thread(
            s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=video_s3_key
        )
        video_bytes = await asyncio.to_thread(response["Body"].read)

        # Determine MIME type from content type or file extension
        content_type = response.get("ContentType", "")
        if content_type and content_type.startswith("video/"):
            mime_type = content_type
        else:
            ext = os.path.splitext(video_s3_key)[1].lower()
            mime_map = {
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".mov": "video/quicktime",
                ".avi": "video/x-msvideo",
                ".mkv": "video/x-matroska",
            }
            mime_type = mime_map.get(ext, "video/mp4")

        logger.info(
            f"[Video Download] Downloaded {len(video_bytes)} bytes, MIME: {mime_type}"
        )
        return video_bytes, mime_type

    except Exception as e:
        logger.error(f"[Video Download] Failed to download video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download video from storage",
        ) from e


async def extract_video_frames(
    video_s3_key: str, frame_interval_seconds: int = 10
) -> list[dict]:
    """
    Download a video from S3 and extract frames at regular intervals.

    Args:
        video_s3_key: S3 key of the video file
        frame_interval_seconds: Interval in seconds between extracted frames (default: 10)

    Returns:
        List of frame dicts with base64_data, timestamp_seconds, and timestamp_label

    Raises:
        HTTPException 400: If no frames could be extracted from the video
        HTTPException 500: If video download or extraction fails
    """
    # Initialize S3 client (same pattern as _llm.py)
    s3_client = (
        boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("LOCAL_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("LOCAL_AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("LOCAL_AWS_SESSION_TOKEN"),
        )
        if os.getenv("LOCAL_AWS_ACCESS_KEY_ID")
        else boto3.client("s3", region_name=AWS_REGION)
    )

    tmp_path: str | None = None
    try:
        # Download video to temp file
        logger.info(f"[Video Extraction] Downloading video from S3: {video_s3_key}")
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".video")
        tmp_path = tmp_file.name

        await asyncio.to_thread(
            s3_client.download_fileobj,
            AWS_ASSET_BUCKET_NAME,
            video_s3_key,
            tmp_file,
        )
        tmp_file.close()

        # Extract frames in thread pool (blocking FFmpeg operations)
        frames = await asyncio.to_thread(
            _extract_frames_sync, tmp_path, frame_interval_seconds
        )

        if not frames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No frames could be extracted from the video",
            )

        return frames

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Video Extraction] Failed to process video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download or extract frames from video",
        ) from e
    finally:
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
