"""Monitoring Time Window Service.

Provides time window checking logic for monitoring runs.
Determines whether monitoring should be skipped based on configured time windows
and the store's timezone.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories import ProjectRepositoryAsync
from utils.log import logger


def parse_time(time_str: str) -> time:
    """
    Parse a time string in HH:MM format to a time object.

    Args:
        time_str: Time string in HH:MM format (e.g., "06:00", "22:30")

    Returns:
        time object representing the parsed time

    Raises:
        ValueError: If the time string is invalid
    """
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}")
        hour = int(parts[0])
        minute = int(parts[1])
        return time(hour=hour, minute=minute)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid time format '{time_str}': {e}") from e


def is_within_time_window(
    current_time: time,
    start_time: time,
    end_time: time,
) -> bool:
    """
    Check if the current time is within the specified time window.

    Handles overnight windows where end_time < start_time (e.g., 22:00-02:00).

    Args:
        current_time: The current time to check
        start_time: Window start time
        end_time: Window end time

    Returns:
        True if current_time is within the window, False otherwise

    Examples:
        - Normal window (06:00-22:00): 10:00 returns True, 23:00 returns False
        - Overnight window (22:00-02:00): 23:00 returns True, 10:00 returns False
    """
    if start_time <= end_time:
        # Normal window (e.g., 06:00-22:00)
        return start_time <= current_time <= end_time
    else:
        # Overnight window (e.g., 22:00-02:00)
        # Current time is valid if it's after start OR before end
        return current_time >= start_time or current_time <= end_time


async def should_skip_monitoring(
    session: AsyncSession,
    project_id: UUID,
    time_window_config: dict | None,
) -> tuple[bool, str | None]:
    """
    Determine if monitoring should be skipped based on time window configuration.

    Args:
        session: Async database session
        project_id: Project UUID to get store timezone from
        time_window_config: Time window configuration dict with keys:
            - enabled: bool
            - start_time: str (HH:MM format)
            - end_time: str (HH:MM format)

    Returns:
        Tuple of (should_skip, reason):
            - should_skip: True if monitoring should be skipped
            - reason: Human-readable reason if skipped, None otherwise

    Note:
        Returns (False, None) if:
        - time_window_config is None or empty
        - enabled is False
        - Store timezone is invalid (falls back to allowing monitoring)
    """
    # If no time window config or not enabled, don't skip
    if not time_window_config:
        return False, None

    enabled = time_window_config.get("enabled", False)
    if not enabled:
        return False, None

    start_time_str = time_window_config.get("start_time")
    end_time_str = time_window_config.get("end_time")

    # If times are not configured, don't skip (shouldn't happen if validation passed)
    if not start_time_str or not end_time_str:
        logger.warning(
            f"[TimeWindow] FAIL-OPEN: Time window enabled but times not configured for project {project_id}. "
            "Allowing monitoring to proceed.",
            extra={
                "fail_open": True,
                "time_window_config": time_window_config,
            },
        )
        return False, None

    try:
        # Parse the configured times
        start_time = parse_time(start_time_str)
        end_time = parse_time(end_time_str)

        # Get store timezone
        project_repo = ProjectRepositoryAsync(session)
        project = await project_repo.get_project(project_id)

        if not project:
            logger.warning(
                f"[TimeWindow] FAIL-OPEN: Project {project_id} not found, skipping time window check. "
                "Allowing monitoring to proceed.",
                extra={
                    "fail_open": True,
                    "time_window_config": time_window_config,
                },
            )
            return False, None

        # Get timezone, default to UTC if not set
        timezone_str = project.timezone or "UTC"

        try:
            tz = ZoneInfo(timezone_str)
        except Exception as e:
            logger.warning(
                f"[TimeWindow] FAIL-OPEN: Invalid timezone '{timezone_str}' for project {project_id}: {e}. "
                "Allowing monitoring to proceed.",
                extra={
                    "fail_open": True,
                    "time_window_config": time_window_config,
                },
            )
            return False, None

        # Get current time in store timezone
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)
        current_time = now_local.time()

        # Check if current time is within the window
        if is_within_time_window(current_time, start_time, end_time):
            return False, None
        else:
            reason = (
                f"Outside monitoring time window ({start_time_str}-{end_time_str} store timezone: {timezone_str}). "
                f"Current time: {current_time.strftime('%H:%M')} {timezone_str}"
            )
            logger.info(
                f"[TimeWindow] Skipping monitoring for project {project_id}: {reason}",
                extra={
                    "project_id": str(project_id),
                    "timezone": timezone_str,
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    "current_time": current_time.strftime("%H:%M"),
                },
            )
            return True, reason

    except ValueError as e:
        logger.warning(
            f"[TimeWindow] FAIL-OPEN: Error parsing time window config for project {project_id}: {e}. "
            "Allowing monitoring to proceed.",
            extra={
                "fail_open": True,
                "time_window_config": time_window_config,
            },
        )
        # On parse error, don't skip (fail open)
        return False, None
    except Exception as e:
        logger.error(
            f"[TimeWindow] FAIL-OPEN: Unexpected error checking time window for project {project_id}: {e}. "
            "Allowing monitoring to proceed.",
            extra={
                "fail_open": True,
                "time_window_config": time_window_config,
            },
            exc_info=True,
        )
        # On unexpected error, don't skip (fail open)
        return False, None
