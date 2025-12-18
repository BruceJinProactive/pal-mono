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


def _normalize_to_naive_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.replace(tzinfo=None)


def extract_resy_availability(
    response: Dict[str, Any], *, party_size: int | None = None
) -> List[Dict[str, Any]]:
    """Return a list of bookable slots from a Resy /4/find response."""

    results = (response.get("results") or {}).get("venues") or []
    slots: List[Dict[str, Any]] = []

    for venue_wrapper in results:
        venue = venue_wrapper.get("venue") or {}
        v_id = venue.get("id")
        venue_id = v_id.get("resy") if isinstance(v_id, dict) else v_id
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
            stype = service.get("type")

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
                    "service_type_id": (
                        stype.get("id") if isinstance(stype, dict) else stype
                    ),
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


def format_resy_availability(
    slots: List[Dict[str, Any]],
    *,
    party_size: int,
    requested_time: datetime.datetime | None,
) -> str:
    """Format available slots in a human-readable way for the agent reply."""

    if not slots:
        return "No availability found."

    venue_name = next((s.get("venue_name") for s in slots if s.get("venue_name")), None)
    header_name = venue_name or "the restaurant"

    lines = [f"Availability for {header_name} (Party of {party_size}):"]

    parsed_times: List[datetime.datetime] = []
    for slot in slots:
        slot_dt = _parse_iso(slot.get("start"))
        if slot_dt:
            normalized = _normalize_to_naive_utc(slot_dt)
            parsed_times.append(normalized.replace(second=0, microsecond=0))

    if not parsed_times:
        return "No availability found."

    unique_times: List[datetime.datetime] = []
    seen: set[datetime.datetime] = set()
    for dt in parsed_times:
        if dt in seen:
            continue
        seen.add(dt)
        unique_times.append(dt)

    center: datetime.datetime | None = None
    if requested_time:
        normalized_requested = _normalize_to_naive_utc(requested_time)
        center = normalized_requested.replace(second=0, microsecond=0)
        unique_times.sort(key=lambda dt: (abs(dt - center), dt))

        if center in unique_times:
            pretty = center.strftime("%A, %B %d, %Y at %I:%M %p")
            return (
                f"Availability for {header_name} (Party of {party_size}):\n"
                f"* {pretty} (requested time is available)"
            )
    else:
        unique_times.sort()

    selected = sorted(unique_times[:5])
    lines.extend(f"* {dt.strftime('%A, %B %d, %Y at %I:%M %p')}" for dt in selected)

    if requested_time and center is not None:
        requested_str = center.strftime("%A, %B %d, %Y at %I:%M %p")
        lines.append(
            f"No exact availability at {requested_str}. Please mention these closest alternatives."
        )
    return "\n".join(lines)


def normalize_reservation_datetime(date: str, time: str) -> str:
    """Return ISO 8601 datetime string from separate date/time components."""

    raw = f"{date}T{time}"
    dt = datetime.datetime.fromisoformat(raw)
    return dt.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def extract_inventory_availability(
    response: Dict[str, Any], *, party_size: int, day: str
) -> List[str]:
    """Extract available times from the inventory API response.

    The inventory API returns availability grouped by date, service, and party size.
    Structure: slots -> <date> -> <service> -> recommendations -> <party_size> -> <config_id> -> [times]

    Returns a sorted, deduplicated list of datetime strings like "2025-12-21 07:00:00".
    """
    slots_by_date = response.get("slots") or {}
    day_data = slots_by_date.get(day) or {}

    available_times: set[str] = set()
    party_size_key = str(party_size)

    for service_data in day_data.values():
        if not isinstance(service_data, dict):
            continue

        recommendations = service_data.get("recommendations") or {}
        party_recommendations = recommendations.get(party_size_key) or {}

        for times_list in party_recommendations.values():
            if isinstance(times_list, list):
                available_times.update(times_list)

    return sorted(available_times)
