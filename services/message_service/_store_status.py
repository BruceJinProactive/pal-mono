"""Compute deterministic store open/closed status for the conversational agent.

``compute_store_status`` resolves status from structured ``business_hours`` (Tier 1),
falls back to a conservative parse of freeform ``store_hours`` text (Tier 2), and
returns open/closed plus raw countdown facts and a spoken summary.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from utils.business_hours import (
    DEFAULT_TIMEZONE,
    is_within_business_hours,
    parse_google_time,
)
from utils.log import logger

_STATUS_OPEN = "open"
_STATUS_CLOSED = "closed"
_STATUS_UNKNOWN = "hours_unknown"

# Sentinel for an all-day ("24 hours") schedule in a parsed store-hours week.
_ALL_DAY = "all_day"

_DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# A full-day line: "Monday: 9:00 AM - 9:00 PM". Grouped lines ("Mon-Fri: ...")
# never match a full day name and are intentionally skipped.
_DAY_LINE_RE = re.compile(
    r"^\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
# A clock token: "9 AM", "9:00 AM", "9:30 PM".
_CLOCK_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", re.IGNORECASE)
# Range separator: hyphen-minus or en-dash.
_RANGE_SEP_RE = re.compile(r"\s*[-–]\s*")


def compute_store_status(
    business_hours: dict | None,
    store_hours_text: str | None,
    timezone_str: str | None,
    now: datetime | None = None,
) -> dict:
    """Compute deterministic store open/closed status with raw countdown facts.

    Two-tier source, never confident-wrong:
      1. Structured ``business_hours`` via ``is_within_business_hours``.
      2. Conservative parse of freeform ``store_hours_text`` (the common case in
         practice, since ``business_hours`` is frequently empty in prod).
      3. Otherwise ``hours_unknown``.

    Emits raw facts only (``minutes_to_close`` / ``closes_at`` / ``minutes_to_open``
    / ``opens_at``) — no ``closing_soon`` and no order-cutoff threshold; that policy
    lives in the prompt. Runs in the voice hot path, so it never raises: any error
    degrades to ``hours_unknown``.

    Args:
        business_hours: JSONB from ``project.business_hours`` (Google Places shape).
        store_hours_text: Freeform text from ``project.store_hours``.
        timezone_str: IANA timezone string from ``project.timezone``.
        now: UTC instant to evaluate (defaults to ``datetime.now(utc)``); pin in tests.

    Returns:
        Dict with keys: ``summary, status, is_open, closes_at, minutes_to_close,
        opens_at, minutes_to_open, source``.
    """
    now = now or datetime.now(timezone.utc)
    tz_name = timezone_str or DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        # Any bad timezone (unknown name, bad path, non-string) falls back to the
        # default, so this setup can't raise before the safety net below is active.
        logger.warning(
            f"Invalid timezone '{timezone_str}', using {DEFAULT_TIMEZONE}",
            extra={"invalid_timezone": timezone_str},
        )
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        tz_name = DEFAULT_TIMEZONE
    local_now = now.astimezone(tz)

    try:
        # Tier 1: structured business_hours. Pass the validated tz_name (not the raw
        # timezone_str): the engine only catches ZoneInfoNotFoundError, so a
        # ValueError-raising tz (e.g. an absolute path) would otherwise escape Tier 1
        # and degrade the whole call to hours_unknown instead of falling back.
        result = is_within_business_hours(now, business_hours, tz_name)
        # The no-data reasons return is_open=True — key off reason, never is_open.
        if result.reason not in {"no_business_hours_data", "no_periods_defined"}:
            if result.is_open:
                close_info = (result.period_info or {}).get("close")
                close_time = time.fromisoformat(close_info) if close_info else None
                if close_time is None:
                    minutes_to_close, closes_at = None, None
                else:
                    minutes_to_close, closes_at = _open_close_facts(
                        close_time, local_now
                    )
                return _finalize(
                    _STATUS_OPEN,
                    local_now,
                    tz_name,
                    source="business_hours",
                    closes_at=closes_at,
                    minutes_to_close=minutes_to_close,
                )
            periods = (business_hours or {}).get("regular_hours", {}).get("periods", [])
            special_by_date = _special_hours_by_date(
                (business_hours or {}).get("special_hours")
            )
            opens_at, opens_day, minutes_to_open = _next_open(
                _openings_from_periods(periods), local_now, special_by_date
            )
            return _finalize(
                _STATUS_CLOSED,
                local_now,
                tz_name,
                source="business_hours",
                opens_at=opens_at,
                opens_day_name=opens_day,
                minutes_to_open=minutes_to_open,
            )

        # Tier 2: conservative parse of freeform store_hours text. Today's line
        # must be confidently parsed (present in the week) or we fall to Tier 3.
        week = _parse_store_hours_week(store_hours_text)
        today = local_now.weekday()
        if week is not None and today in week:
            open_now, close_time = _open_now_from_week(week, local_now)
            if open_now:
                if close_time is None:  # all-day ("24 hours")
                    minutes_to_close, closes_at = None, None
                else:
                    minutes_to_close, closes_at = _open_close_facts(
                        close_time, local_now
                    )
                return _finalize(
                    _STATUS_OPEN,
                    local_now,
                    tz_name,
                    source="store_hours_text",
                    closes_at=closes_at,
                    minutes_to_close=minutes_to_close,
                )
            opens_at, opens_day, minutes_to_open = _next_open(
                _openings_from_week(week), local_now
            )
            return _finalize(
                _STATUS_CLOSED,
                local_now,
                tz_name,
                source="store_hours_text",
                opens_at=opens_at,
                opens_day_name=opens_day,
                minutes_to_open=minutes_to_open,
            )

        # Tier 3: nothing usable.
        return _hours_unknown(local_now, tz_name)
    except Exception:
        logger.exception("compute_store_status failed; returning hours_unknown")
        return _hours_unknown(local_now, tz_name)


def _open_close_facts(
    close_time: time, local_now: datetime
) -> tuple[int | None, str | None]:
    """Return ``(minutes_to_close, closes_at_12h)`` for an open store.

    Roll-forward handles same-day and overnight uniformly: a close earlier than
    ``local_now`` (an overnight close already past today) rolls to tomorrow.
    """
    closes_dt = datetime.combine(local_now.date(), close_time, tzinfo=local_now.tzinfo)
    if closes_dt < local_now:
        closes_dt += timedelta(days=1)
    minutes_to_close = int((closes_dt - local_now).total_seconds() // 60)
    return minutes_to_close, _to_12h(close_time)


def _special_hours_by_date(
    special_hours: list[dict] | None,
) -> dict[str, list[dict]]:
    """Map Google ``special_hours`` entries by ISO date string.

    The value is that date's period list; an empty list means closed. Dates absent
    from the map fall back to the regular weekly schedule.
    """
    by_date: dict[str, list[dict]] = {}
    for entry in special_hours or []:
        date_str = entry.get("date")
        if date_str:
            by_date[date_str] = entry.get("periods", [])
    return by_date


def _next_open(
    openings: list[tuple[int, time]],
    local_now: datetime,
    special_by_date: dict[str, list[dict]] | None = None,
) -> tuple[str | None, str | None, int | None]:
    """Return ``(opens_at_12h, opens_day_name, minutes_to_open)`` for the soonest
    future opening, or ``(None, None, None)`` if none found.

    ``openings`` is a list of weekly opening instants ``(python_weekday, time)``.
    Scans day-offsets 0..7 (d=0 covers "closed now, opens later today").

    ``special_by_date`` (ISO date -> Google periods) overrides the regular schedule
    for that exact date: an empty list means closed (the day is skipped), non-empty
    periods supply that date's actual opening time(s). This keeps holiday closures
    and exceptional-hours days from being announced as the next opening.
    """
    special_by_date = special_by_date or {}
    best: datetime | None = None
    for d in range(8):
        candidate_date = local_now.date() + timedelta(days=d)
        special_periods = special_by_date.get(candidate_date.isoformat())
        if special_periods is not None:
            # Special hours replace the regular schedule for this exact date.
            for period in special_periods:
                open_info = period.get("open", {})
                open_time = parse_google_time(open_info.get("time", "0000"))
                candidate = datetime.combine(
                    candidate_date, open_time, tzinfo=local_now.tzinfo
                )
                if candidate > local_now and (best is None or candidate < best):
                    best = candidate
            continue
        target_wd = (local_now.weekday() + d) % 7
        for weekday, open_time in openings:
            if weekday != target_wd:
                continue
            candidate = datetime.combine(
                candidate_date, open_time, tzinfo=local_now.tzinfo
            )
            if candidate > local_now and (best is None or candidate < best):
                best = candidate
    if best is None:
        return None, None, None
    minutes_to_open = int((best - local_now).total_seconds() // 60)
    return _to_12h(best.time()), best.strftime("%A"), minutes_to_open


def _open_now_from_week(
    week: dict[int, list[tuple[time, time]] | str],
    local_now: datetime,
) -> tuple[bool, time | None]:
    """Determine open-now from a parsed week.

    Returns ``(is_open, close_time)``; ``close_time`` is ``None`` for an all-day
    schedule. Checks today's ranges plus a best-effort yesterday-overnight spillover.
    """
    today = local_now.weekday()
    now_t = local_now.time()

    today_val = week.get(today)
    if today_val == _ALL_DAY:
        return True, None
    if isinstance(today_val, list):
        for open_t, close_t in today_val:
            if close_t <= open_t:  # overnight range, pre-midnight portion today
                if now_t >= open_t:
                    return True, close_t
            elif open_t <= now_t <= close_t:
                return True, close_t

    # Best-effort yesterday-overnight spillover (after-midnight closing portion).
    yesterday_val = week.get((today - 1) % 7)
    if isinstance(yesterday_val, list) and yesterday_val:
        last_open, last_close = yesterday_val[-1]
        if last_close <= last_open and now_t <= last_close:
            return True, last_close

    return False, None


def _openings_from_periods(periods: list[dict]) -> list[tuple[int, time]]:
    """Adapt Google ``regular_hours.periods`` to ``(python_weekday, open_time)``."""
    openings: list[tuple[int, time]] = []
    for period in periods:
        open_info = period.get("open", {})
        google_day = open_info.get("day")
        if google_day is None:
            continue
        openings.append(
            (
                _google_day_to_python(google_day),
                parse_google_time(open_info.get("time", "0000")),
            )
        )
    return openings


def _openings_from_week(
    week: dict[int, list[tuple[time, time]] | str],
) -> list[tuple[int, time]]:
    """Adapt a parsed week to ``(python_weekday, open_time)`` opening instants.

    Skips closed days (``[]``) and the all-day sentinel (an all-day day is open,
    not "opening at a time").
    """
    openings: list[tuple[int, time]] = []
    for weekday, ranges in week.items():
        if not isinstance(ranges, list):
            continue
        for open_t, _close_t in ranges:
            openings.append((weekday, open_t))
    return openings


def _google_day_to_python(google_day: int) -> int:
    """Invert the module's ``(python + 1) % 7`` Google-day convention."""
    return (google_day - 1) % 7


def _to_12h(t: time) -> str:
    """Format a time as a 12-hour string, e.g. ``"9:30 PM"`` (cross-platform)."""
    hour = (t.hour % 12) or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour}:{t.minute:02d} {suffix}"


def _build_summary(
    status: str,
    local_now: datetime,
    tz_name: str,
    closes_at_12h: str | None,
    opens_at_12h: str | None,
    opens_day_name: str | None,
) -> str:
    """Build the factual, self-contained spoken summary line."""
    if status == _STATUS_UNKNOWN:
        return (
            "Store hours could not be determined automatically; "
            "use the Store Hours listed in the prompt."
        )

    when = f"{local_now.strftime('%a')} {_to_12h(local_now.time())}, {tz_name}"

    if status == _STATUS_OPEN:
        if closes_at_12h is None:  # all-day
            return f"Store is OPEN now ({when})."
        return f"Store is OPEN now ({when}). Closes {closes_at_12h}."

    # status == closed
    if opens_at_12h is None:
        return f"Store is CLOSED now ({when})."
    return f"Store is CLOSED now ({when}). Opens {opens_at_12h} {opens_day_name}."


def _finalize(
    status: str,
    local_now: datetime,
    tz_name: str,
    *,
    source: str,
    closes_at: str | None = None,
    minutes_to_close: int | None = None,
    opens_at: str | None = None,
    opens_day_name: str | None = None,
    minutes_to_open: int | None = None,
) -> dict:
    """Assemble the output contract dict, enforcing mutual exclusivity by status."""
    if status == _STATUS_OPEN:
        opens_at = opens_day_name = None
        minutes_to_open = None
    elif status == _STATUS_CLOSED:
        closes_at = None
        minutes_to_close = None

    summary = _build_summary(
        status,
        local_now,
        tz_name,
        closes_at,
        opens_at,
        opens_day_name,
    )
    return {
        "summary": summary,
        "status": status,
        "is_open": status == _STATUS_OPEN,
        "closes_at": closes_at,
        "minutes_to_close": minutes_to_close,
        "opens_at": opens_at,
        "minutes_to_open": minutes_to_open,
        "source": source,
    }


def _hours_unknown(local_now: datetime, tz_name: str) -> dict:
    """Build the ``hours_unknown`` contract dict (Tier 3 / error fallback)."""
    return _finalize(_STATUS_UNKNOWN, local_now, tz_name, source="none")


def _parse_store_hours_week(
    text: str | None,
) -> dict[int, list[tuple[time, time]] | str] | None:
    """Conservatively parse freeform store-hours text into a per-weekday schedule.

    Keyed by Python weekday (Mon=0..Sun=6). Each value is a list of one or more
    canonical ``(open, close)`` ranges, ``[]`` for an explicit closure, or the ``_ALL_DAY``
    sentinel. A day whose value cannot be cleanly parsed is left absent (never
    confident-wrong). Returns ``None`` only when there is no text at all; the
    caller decides whether today's line is present.
    """
    if not text:
        return None

    # Google Places weekday_text puts U+202F (narrow no-break space) before AM/PM.
    normalized = text.replace("\u202f", " ").replace("\u00a0", " ")
    week: dict[int, list[tuple[time, time]] | str] = {}
    for line in normalized.split("\n"):
        match = _DAY_LINE_RE.match(line)
        if not match:
            continue
        weekday = _DAY_NAMES[match.group(1).lower()]
        parsed = _parse_day_value(match.group(2))
        if parsed is None:  # unparseable value -> leave the day absent
            continue
        week[weekday] = parsed
    return week


def _parse_day_value(value: str) -> list[tuple[time, time]] | str | None:
    """Parse a single day's value into ranges, ``[]`` (closed), or ``_ALL_DAY``.

    Returns ``None`` if any token fails to parse (the whole line is then untrusted).
    """
    normalized = value.strip().lower()
    if normalized == "closed":
        return []
    if normalized in {"open 24 hours", "open 24 hrs"}:
        return _ALL_DAY

    ranges: list[tuple[time, time]] = []
    for token in value.split(","):
        parts = [p for p in _RANGE_SEP_RE.split(token.strip()) if p.strip()]
        if len(parts) != 2:
            return None
        open_t = _parse_clock_token(parts[0])
        close_t = _parse_clock_token(parts[1])
        if open_t is None or close_t is None:
            return None
        ranges.append((open_t, close_t))
    if not ranges:
        return None
    return ranges


def _parse_clock_token(token: str) -> time | None:
    """Parse a single 12-hour clock token with AM/PM."""
    match = _CLOCK_RE.match(token.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    meridiem = match.group(3).lower()
    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return None
    if meridiem == "am":
        hour = 0 if hour == 12 else hour
    else:  # pm
        hour = 12 if hour == 12 else hour + 12
    return time(hour, minute)
