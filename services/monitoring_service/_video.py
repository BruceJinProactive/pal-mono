"""Monitoring Service Video Frame Extraction.

Downloads video files from S3 and extracts frames at regular intervals
using PyAV for use in VLM-based monitoring analysis.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import av
import boto3
from fastapi import HTTPException, status
from PIL import Image

from utils.log import logger

# Codecs that can be remuxed into an MP4 container without re-encoding.
_MP4_COMPATIBLE_CODECS: set[str] = {"h264", "hevc", "h265", "mpeg4", "av1"}
ONE_MINUTE_VIDEO_SECONDS = 60.0
ONE_MINUTE_VIDEO_MIN_SECONDS = 59.0
ONE_MINUTE_VIDEO_MAX_SECONDS = 65.0
END_FRAME_SAFETY_MARGIN_SECONDS = 0.5
VIDEO_LOOKUP_PRESIGN_EXPIRES_SECONDS = 3600
_VIDEO_FILENAME_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"
    r"\.(?:mp4|mov|mkv|avi|webm)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CameraVideoSegment:
    """Presigned camera video segment discovered from archive storage."""

    s3_key: str
    url: str
    segment_start_time: datetime
    segment_end_time: datetime


def _duration_seconds(container: Any, stream: Any) -> float:
    """Return the best available duration for a video container."""
    if stream.duration and stream.time_base:
        return float(stream.duration * stream.time_base)
    if container.duration:
        return container.duration / 1_000_000.0
    return 0.0


def _timestamp_label(timestamp_seconds: float) -> str:
    minutes = int(timestamp_seconds) // 60
    seconds = int(timestamp_seconds) % 60
    return f"{minutes}:{seconds:02d}"


def _frame_to_jpeg_bytes(frame: Any, timestamp_seconds: float) -> bytes | None:
    try:
        pil_image = frame.to_image()
        image_mode = getattr(pil_image, "mode", "RGB")
        if isinstance(image_mode, str) and image_mode != "RGB":
            pil_image = pil_image.convert("RGB")

        width, height = pil_image.size
        if width < 10 or height < 10:
            logger.warning(
                f"[Video Extraction] Frame at {timestamp_seconds}s too small ({width}x{height}), skipping"
            )
            return None

        if width > 4096 or height > 4096:
            logger.warning(
                f"[Video Extraction] Frame at {timestamp_seconds}s too large ({width}x{height}), resizing"
            )
            pil_image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85)
        jpeg_bytes = buffer.getvalue()

        if len(jpeg_bytes) < 100:
            logger.warning(
                f"[Video Extraction] Frame at {timestamp_seconds}s produced suspiciously small JPEG ({len(jpeg_bytes)} bytes), skipping"
            )
            return None

        try:
            Image.open(BytesIO(jpeg_bytes)).verify()
        except Exception as verify_error:
            logger.warning(
                f"[Video Extraction] Frame at {timestamp_seconds}s failed JPEG verification: {verify_error}, skipping"
            )
            return None

        return jpeg_bytes
    except Exception as frame_error:
        logger.warning(
            f"[Video Extraction] Error processing frame at {timestamp_seconds}s: {frame_error}, skipping"
        )
        return None


def _validate_one_minute_duration(duration_seconds: float) -> None:
    if duration_seconds <= 0:
        raise ValueError("Could not determine video duration")

    if (
        not ONE_MINUTE_VIDEO_MIN_SECONDS
        <= duration_seconds
        <= ONE_MINUTE_VIDEO_MAX_SECONDS
    ):
        raise ValueError(
            "Archive-only videos must be between "
            f"{ONE_MINUTE_VIDEO_MIN_SECONDS:.0f} and "
            f"{ONE_MINUTE_VIDEO_MAX_SECONDS:.0f} seconds long "
            f"(detected {duration_seconds:.2f}s)"
        )


def remux_to_mp4(src: bytes) -> bytes:
    """Remux a video file (e.g. MKV) into an MP4 container.

    If the source video codec is MP4-compatible (H.264, HEVC, etc.) the
    packets are copied directly — no re-encoding, so it's fast and lossless.
    If the codec is incompatible (VP8/VP9), the video is re-encoded to H.264.

    Args:
        src: Raw bytes of the source video file.

    Returns:
        Raw bytes of the MP4-remuxed video.

    Raises:
        ValueError: If the source contains no video stream.
    """
    input_buf = BytesIO(src)
    output_buf = BytesIO()

    input_container = av.open(input_buf, mode="r")
    try:
        if not input_container.streams.video:
            raise ValueError("Source video contains no video stream")

        src_video = input_container.streams.video[0]
        codec_name = src_video.codec_context.name or ""
        needs_reencode = codec_name.lower() not in _MP4_COMPATIBLE_CODECS

        output_container = av.open(output_buf, mode="w", format="mp4")
        try:
            if needs_reencode:
                logger.info(
                    f"[Video Remux] Codec '{codec_name}' not MP4-compatible, re-encoding to H.264"
                )
                out_video = output_container.add_stream(
                    "libx264", rate=src_video.average_rate or 30
                )
                out_video.width = src_video.codec_context.width
                out_video.height = src_video.codec_context.height
                out_video.pix_fmt = "yuv420p"

                for frame in input_container.decode(video=0):
                    for packet in out_video.encode(frame):
                        output_container.mux(packet)
                # Flush encoder
                for packet in out_video.encode():
                    output_container.mux(packet)
            else:
                logger.info(
                    f"[Video Remux] Codec '{codec_name}' is MP4-compatible, remuxing (no re-encode)"
                )
                out_video = output_container.add_stream_from_template(src_video)

                for packet in input_container.demux(src_video):
                    if packet.dts is None:
                        continue
                    packet.stream = out_video
                    output_container.mux(packet)

            # Copy audio streams if present
            if input_container.streams.audio:
                src_audio = input_container.streams.audio[0]
                out_audio = output_container.add_stream_from_template(src_audio)
                # Re-demux to get audio packets
                input_container.seek(0)
                for packet in input_container.demux(src_audio):
                    if packet.dts is None:
                        continue
                    packet.stream = out_audio
                    output_container.mux(packet)
        finally:
            output_container.close()
    finally:
        input_container.close()

    logger.info(
        f"[Video Remux] Remuxed {len(src)} bytes -> {output_buf.tell()} bytes (MP4)"
    )
    return output_buf.getvalue()


# AWS Configuration (reuse same env vars as _llm.py)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ASSET_BUCKET_NAME = os.getenv("AWS_ASSET_BUCKET_NAME")


def _create_video_s3_client() -> Any:
    return (
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


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_video_prefix(video_prefix: str) -> str:
    return video_prefix if video_prefix.endswith("/") else f"{video_prefix}/"


def _video_date_prefixes(
    video_prefix: str,
    start_time: datetime,
    end_time: datetime,
) -> list[str]:
    prefix = _normalize_video_prefix(video_prefix)
    current_date = start_time.date()
    end_date = end_time.date()
    prefixes: list[str] = []

    while current_date <= end_date:
        prefixes.append(f"{prefix}{current_date.isoformat()}/")
        current_date += timedelta(days=1)

    return prefixes


def _parse_video_segment_start(s3_key: str) -> datetime | None:
    filename = s3_key.rsplit("/", 1)[-1]
    match = _VIDEO_FILENAME_RE.match(filename)
    if match is None:
        return None

    try:
        return datetime.strptime(
            match.group("timestamp"),
            "%Y-%m-%d_%H-%M-%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _segments_overlap(
    segment_start_time: datetime,
    segment_end_time: datetime,
    window_start_time: datetime,
    window_end_time: datetime,
) -> bool:
    return segment_start_time < window_end_time and segment_end_time > window_start_time


def _lookup_camera_video_segments_sync(
    s3_client: Any,
    bucket_name: str,
    video_prefix: str,
    start_time: datetime,
    end_time: datetime,
    segment_duration_seconds: float,
) -> list[CameraVideoSegment]:
    search_start_time = start_time - timedelta(seconds=segment_duration_seconds)
    prefixes = _video_date_prefixes(video_prefix, search_start_time, end_time)
    paginator = s3_client.get_paginator("list_objects_v2")
    videos: list[CameraVideoSegment] = []

    for prefix in prefixes:
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key")
                if not isinstance(key, str):
                    continue

                segment_start_time = _parse_video_segment_start(key)
                if segment_start_time is None:
                    continue

                segment_end_time = segment_start_time + timedelta(
                    seconds=segment_duration_seconds
                )
                if not _segments_overlap(
                    segment_start_time,
                    segment_end_time,
                    start_time,
                    end_time,
                ):
                    continue

                url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket_name, "Key": key},
                    ExpiresIn=VIDEO_LOOKUP_PRESIGN_EXPIRES_SECONDS,
                )
                if not isinstance(url, str) or not url:
                    continue

                videos.append(
                    CameraVideoSegment(
                        s3_key=key,
                        url=url,
                        segment_start_time=segment_start_time,
                        segment_end_time=segment_end_time,
                    )
                )

    return sorted(videos, key=lambda video: (video.segment_start_time, video.s3_key))


async def lookup_camera_video_segments(
    video_prefix: str,
    start_time: datetime,
    end_time: datetime,
    segment_duration_seconds: float = ONE_MINUTE_VIDEO_SECONDS,
) -> list[CameraVideoSegment]:
    """Find archived camera videos whose segment windows overlap the event window."""
    bucket_name = AWS_ASSET_BUCKET_NAME
    if not bucket_name:
        logger.warning("[Video Lookup] AWS_ASSET_BUCKET_NAME is not configured")
        return []
    if segment_duration_seconds <= 0:
        return []

    window_start_time = _as_utc_datetime(start_time)
    window_end_time = _as_utc_datetime(end_time)
    if window_start_time >= window_end_time:
        return []

    s3_client = _create_video_s3_client()
    try:
        return await asyncio.to_thread(
            _lookup_camera_video_segments_sync,
            s3_client,
            bucket_name,
            video_prefix,
            window_start_time,
            window_end_time,
            segment_duration_seconds,
        )
    except Exception as e:
        logger.warning(f"[Video Lookup] Failed to find matching videos: {e}")
        return []


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
        duration_seconds = _duration_seconds(container, stream)
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
                    try:
                        jpeg_bytes = _frame_to_jpeg_bytes(frame, target_ts)
                        if jpeg_bytes is None:
                            continue

                        # Format timestamp label
                        timestamp_label = _timestamp_label(target_ts)

                        frames.append(
                            {
                                "base64_data": base64.b64encode(jpeg_bytes).decode(
                                    "utf-8"
                                ),
                                "timestamp_seconds": target_ts,
                                "timestamp_label": timestamp_label,
                            }
                        )
                        logger.debug(
                            f"[Video Extraction] Successfully extracted frame at {target_ts}s ({len(jpeg_bytes)} bytes)"
                        )
                        break  # Only need one frame per timestamp
                    except Exception as frame_error:
                        logger.warning(
                            f"[Video Extraction] Error processing frame at {target_ts}s: {frame_error}, skipping"
                        )
                        continue

            except Exception as e:
                logger.warning(
                    f"[Video Extraction] Failed to extract frame at {target_ts}s: {e}"
                )
                continue

    finally:
        container.close()

    logger.info(f"[Video Extraction] Extracted {len(frames)} frames from video")
    return frames


def _extract_frames_at_timestamps_sync(
    video_path: str,
    timestamps_seconds: tuple[float, ...],
    require_one_minute: bool = False,
) -> tuple[float, list[dict[str, Any]]]:
    """
    Extract JPEG frames from a local video at exact timestamp labels.

    If a requested timestamp lands at or beyond the duration boundary, PyAV may
    not decode a frame exactly there. In that case, seek just before the end but
    preserve the requested timestamp label in the returned frame metadata.
    """
    frames: list[dict[str, Any]] = []

    container = av.open(video_path)
    try:
        if not container.streams.video:
            raise ValueError("Source video contains no video stream")

        stream = container.streams.video[0]
        duration_seconds = _duration_seconds(container, stream)
        if require_one_minute:
            _validate_one_minute_duration(duration_seconds)

        for timestamp_seconds in timestamps_seconds:
            seek_timestamp = timestamp_seconds
            if duration_seconds > 0 and timestamp_seconds >= duration_seconds:
                seek_timestamp = max(
                    duration_seconds - END_FRAME_SAFETY_MARGIN_SECONDS,
                    0.0,
                )

            try:
                time_base = stream.time_base or 1
                target_pts = int(seek_timestamp / time_base)
                container.seek(target_pts, stream=stream)

                for frame in container.decode(video=0):
                    jpeg_bytes = _frame_to_jpeg_bytes(frame, timestamp_seconds)
                    if jpeg_bytes is None:
                        continue

                    frames.append(
                        {
                            "jpeg_bytes": jpeg_bytes,
                            "base64_data": base64.b64encode(jpeg_bytes).decode("utf-8"),
                            "timestamp_seconds": timestamp_seconds,
                            "timestamp_label": _timestamp_label(timestamp_seconds),
                            "source_timestamp_seconds": seek_timestamp,
                        }
                    )
                    break
            except Exception as e:
                logger.warning(
                    f"[Video Extraction] Failed to extract exact frame at {timestamp_seconds}s: {e}"
                )
                continue
    finally:
        container.close()

    if len(frames) != len(timestamps_seconds):
        raise ValueError(
            f"Expected {len(timestamps_seconds)} frames, extracted {len(frames)}"
        )

    return duration_seconds, frames


def extract_one_minute_video_frames_from_bytes(
    video_bytes: bytes,
    timestamps_seconds: tuple[float, ...] = (15.0, 30.0, 45.0, 60.0),
) -> tuple[float, list[dict[str, Any]]]:
    """Validate one-minute video bytes and extract archive frame JPEGs."""
    if not video_bytes:
        raise ValueError("Provided video bytes are empty (0 bytes)")

    tmp_path: str | None = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".video")
        tmp_path = tmp_file.name
        tmp_file.write(video_bytes)
        tmp_file.close()

        return _extract_frames_at_timestamps_sync(
            tmp_path,
            timestamps_seconds,
            require_one_minute=True,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
