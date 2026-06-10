"""Utilities for deriving camera capture time from snapshot paths."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

CAPTURE_FILENAME_FORMAT = "%Y-%m-%d_%H-%M-%S"


def parse_utc_capture_time_from_path(path: str | None) -> datetime | None:
    """Parse UTC capture timestamps from snapshot filenames or S3 keys."""
    if not path:
        return None

    stripped_path = path.strip()
    if not stripped_path:
        return None

    parsed = urlsplit(stripped_path)
    path_without_query = (
        parsed.path if parsed.scheme else stripped_path.split("?", maxsplit=1)[0]
    )
    filename = os.path.basename(path_without_query.rstrip("/"))
    stem, _ = os.path.splitext(filename)

    try:
        return datetime.strptime(stem, CAPTURE_FILENAME_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
