from __future__ import annotations

from datetime import datetime, timezone

import pytest

from utils.vision_capture_time import parse_utc_capture_time_from_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "snapshots/2026-06-09/2026-06-09_18-51-35.jpg",
            datetime(2026, 6, 9, 18, 51, 35, tzinfo=timezone.utc),
        ),
        (
            "security/cameras/account/project/Main Dining Room/images/"
            "2026-06-09/2026-06-09_18-51-35.jpeg",
            datetime(2026, 6, 9, 18, 51, 35, tzinfo=timezone.utc),
        ),
        (
            "https://example-bucket.s3.amazonaws.com/security/cameras/cam/images/"
            "2026-06-09/2026-06-09_18-51-35.jpg?X-Amz-Signature=abc",
            datetime(2026, 6, 9, 18, 51, 35, tzinfo=timezone.utc),
        ),
        ("snapshots/2026-06-09/frame.jpg", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_utc_capture_time_from_path(
    path: str | None, expected: datetime | None
) -> None:
    assert parse_utc_capture_time_from_path(path) == expected
