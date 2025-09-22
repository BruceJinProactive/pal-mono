"""Utility helpers for Resy reservation workflows."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List


def _parse_iso(dt_str: str | None) -> datetime.datetime | None:
    if not dt_str:
        return None

    normalized = dt_str.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def extract_resy_availability(
    response: Dict[str, Any], *, party_size: int | None = None
) -> List[Dict[str, Any]]:
    """Return a list of bookable slots from a Resy /4/find response."""

    results = (response.get("results") or {}).get("venues") or []
    slots: List[Dict[str, Any]] = []

    for venue_wrapper in results:
        venue = venue_wrapper.get("venue") or {}
        venue_id = (venue.get("id") or {}).get("resy")
        venue_name = venue.get("name")
        timezone_str = (venue.get("location") or {}).get("time_zone")

        for slot in venue_wrapper.get("slots") or []:
            availability = slot.get("availability") or {}
            status = slot.get("status") or {}
            quantity = slot.get("quantity") or 0

            if availability.get("id") != 3:
                continue
            if status.get("id") != 1:
                continue
            if quantity <= 0:
                continue

            size = slot.get("size") or {}
            min_size = size.get("min")
            max_size = size.get("max")

            if party_size is not None:
                if min_size is not None and party_size < min_size:
                    continue
                if max_size is not None and party_size > max_size:
                    continue

            config = slot.get("config") or {}
            shift = slot.get("shift") or {}
            service = shift.get("service") or {}

            slots.append(
                {
                    "venue_id": venue_id,
                    "venue_name": venue_name,
                    "timezone": timezone_str,
                    "start": (slot.get("date") or {}).get("start"),
                    "end": (slot.get("date") or {}).get("end"),
                    "quantity": quantity,
                    "token": config.get("token"),
                    "area": config.get("type"),
                    "service_type_id": (service.get("type") or {}).get("id"),
                    "template_id": (slot.get("template") or {}).get("id"),
                }
            )

    slots.sort(key=lambda s: (s.get("start") or "", s.get("token") or ""))
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in slots:
        key = (item.get("start"), item.get("token"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


def format_resy_availability(slots: List[Dict[str, Any]], *, party_size: int) -> str:
    """Format available slots in a human-readable way for the agent reply."""

    if not slots:
        return "No availability found."

    venue_name = next((s.get("venue_name") for s in slots if s.get("venue_name")), None)
    header_name = venue_name or "the restaurant"

    lines = [f"Availability for {header_name} (Party of {party_size}):"]

    seen_times: set[str] = set()
    for slot in slots:
        start_dt = _parse_iso(slot.get("start"))
        if start_dt:
            pretty_time = start_dt.strftime("%A, %B %d, %Y at %I:%M %p")
        else:
            pretty_time = slot.get("start") or "Unknown time"

        if pretty_time in seen_times:
            continue
        seen_times.add(pretty_time)
        lines.append(f"* {pretty_time}")
        if len(lines) >= 8:  # header + up to 7 slots keeps output concise
            break

    return "\n".join(lines)


def normalize_reservation_datetime(date: str, time: str) -> str:
    """Return ISO 8601 datetime string from separate date/time components."""

    raw = f"{date}T{time}"
    dt = datetime.datetime.fromisoformat(raw)
    return dt.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
