"""Tests for compute_store_status (services.message_service._store_status)."""

from datetime import datetime, time, timezone

from services.message_service._store_status import _to_12h, compute_store_status

# 2024-06-16 Sun, 06-17 Mon, 06-18 Tue, 06-19 Wed, 06-21 Fri, 06-22 Sat.
_UTC = timezone.utc
_EXPECTED_KEYS = {
    "summary",
    "status",
    "is_open",
    "closes_at",
    "minutes_to_close",
    "opens_at",
    "minutes_to_open",
    "source",
}


def _mon(hour: int, minute: int = 0) -> datetime:
    """A pinned Monday (2024-06-17) UTC instant."""
    return datetime(2024, 6, 17, hour, minute, tzinfo=_UTC)


def _bh(periods: list[dict]) -> dict:
    """Wrap Google-format periods in a business_hours dict."""
    return {"regular_hours": {"periods": periods}}


# Monday 09:00-22:00 (Google Monday = 1).
_MON_9_22 = _bh(
    [{"open": {"day": 1, "time": "0900"}, "close": {"day": 1, "time": "2200"}}]
)


class TestTo12h:
    """Tests for _to_12h — cross-platform 12-hour formatting."""

    def test_evening(self) -> None:
        assert _to_12h(time(21, 30)) == "9:30 PM"

    def test_midnight(self) -> None:
        assert _to_12h(time(0, 0)) == "12:00 AM"

    def test_noon(self) -> None:
        assert _to_12h(time(12, 0)) == "12:00 PM"

    def test_morning(self) -> None:
        assert _to_12h(time(9, 0)) == "9:00 AM"


class TestComputeStoreStatusTier1:
    """Tier 1 — structured business_hours."""

    def test_open_far_close(self) -> None:
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(12))
        assert r["status"] == "open"
        assert r["is_open"] is True
        assert r["source"] == "business_hours"
        assert r["closes_at"] == "10:00 PM"
        assert r["minutes_to_close"] == 600
        assert r["opens_at"] is None
        assert r["minutes_to_open"] is None

    def test_open_near_close_still_open(self) -> None:
        bh = _bh(
            [{"open": {"day": 1, "time": "0900"}, "close": {"day": 1, "time": "2130"}}]
        )
        r = compute_store_status(bh, None, "UTC", now=_mon(21, 12))
        assert r["status"] == "open"  # never "closing_soon"
        assert "closing_soon" not in r
        assert r["closes_at"] == "9:30 PM"
        assert r["minutes_to_close"] == 18

    def test_overnight_before_midnight(self) -> None:
        # Fri 22:00 - Sat 02:00 (Google Fri=5, Sat=6); now Fri 23:00.
        bh = _bh(
            [{"open": {"day": 5, "time": "2200"}, "close": {"day": 6, "time": "0200"}}]
        )
        r = compute_store_status(
            bh, None, "UTC", now=datetime(2024, 6, 21, 23, 0, tzinfo=_UTC)
        )
        assert r["status"] == "open"
        assert r["closes_at"] == "2:00 AM"
        assert r["minutes_to_close"] == 180

    def test_overnight_after_midnight(self) -> None:
        # Same period; now Sat 01:00 (closing portion).
        bh = _bh(
            [{"open": {"day": 5, "time": "2200"}, "close": {"day": 6, "time": "0200"}}]
        )
        r = compute_store_status(
            bh, None, "UTC", now=datetime(2024, 6, 22, 1, 0, tzinfo=_UTC)
        )
        assert r["status"] == "open"
        assert r["closes_at"] == "2:00 AM"
        assert r["minutes_to_close"] == 60

    def test_closed_with_next_open(self) -> None:
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(6))
        assert r["status"] == "closed"
        assert r["is_open"] is False
        assert r["source"] == "business_hours"
        assert r["opens_at"] == "9:00 AM"
        assert r["minutes_to_open"] == 180
        assert r["closes_at"] is None
        assert r["minutes_to_close"] is None

    def test_closed_no_future_period_opens_null(self) -> None:
        # Periods present (so not no_periods_defined) but lacking a "day" -> no opening instant.
        bh = _bh([{"open": {"time": "0900"}, "close": {"time": "2200"}}])
        r = compute_store_status(bh, None, "UTC", now=_mon(12))
        assert r["status"] == "closed"
        assert r["opens_at"] is None
        assert r["minutes_to_open"] is None

    def test_empty_business_hours_falls_through_not_open(self) -> None:
        # reason=no_business_hours_data returns is_open=True; must NOT be reported open.
        r = compute_store_status({}, None, "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"
        assert r["is_open"] is False

    def test_no_periods_falls_through_not_open(self) -> None:
        r = compute_store_status(_bh([]), None, "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"
        assert r["is_open"] is False


class TestComputeStoreStatusSpecialHours:
    """Next-open honors date-keyed special hours (holiday closures / exceptions)."""

    _DAILY_12_23 = [
        {"open": {"day": d, "time": "1200"}, "close": {"day": d, "time": "2300"}}
        for d in range(7)
    ]
    _DAILY_9_17 = [
        {"open": {"day": d, "time": "0900"}, "close": {"day": d, "time": "1700"}}
        for d in range(7)
    ]

    def test_next_open_skips_special_closures(self) -> None:
        # Real shape from dintaifung-manhattan: closed Tue 5/12, Wed 5/13, Thu 5/14.
        # Regular schedule opens daily at noon; without special-awareness the agent
        # would wrongly announce "opens 12 PM Tuesday" (a closed day).
        bh = {
            "regular_hours": {"periods": self._DAILY_12_23},
            "special_hours": [
                {"date": "2026-05-12", "periods": [], "exceptional_hours": True},
                {"date": "2026-05-13", "periods": [], "exceptional_hours": True},
                {"date": "2026-05-14", "periods": [], "exceptional_hours": True},
            ],
        }
        r = compute_store_status(
            bh, None, "UTC", now=datetime(2026, 5, 12, 9, 0, tzinfo=_UTC)
        )
        assert r["status"] == "closed"
        assert r["opens_at"] == "12:00 PM"
        assert "Friday" in r["summary"]  # 5/15 — the first non-closed day
        assert "Tuesday" not in r["summary"]

    def test_next_open_uses_special_modified_hours(self) -> None:
        # Real shape from mikiya_las_vegas: a date with exceptional (non-empty) hours.
        # Regular opens 9 AM; the special day opens later at 1 PM -> use the special time.
        bh = {
            "regular_hours": {"periods": self._DAILY_9_17},
            "special_hours": [
                {
                    "date": "2026-05-12",
                    "periods": [{"open": {"time": "1300"}, "close": {"time": "2100"}}],
                    "exceptional_hours": True,
                }
            ],
        }
        r = compute_store_status(
            bh, None, "UTC", now=datetime(2026, 5, 12, 8, 0, tzinfo=_UTC)
        )
        assert r["status"] == "closed"
        assert r["opens_at"] == "1:00 PM"  # special time, not the regular 9 AM


class TestComputeStoreStatusTier2:
    """Tier 2 — conservative parse of freeform store_hours text."""

    def test_hyphen_open(self) -> None:
        r = compute_store_status(None, "Monday: 9:00 AM - 9:00 PM", "UTC", now=_mon(12))
        assert r["status"] == "open"
        assert r["source"] == "store_hours_text"
        assert r["closes_at"] == "9:00 PM"
        assert r["minutes_to_close"] == 540

    def test_en_dash_open(self) -> None:
        r = compute_store_status(
            None, "Monday: 9:00 AM \u2013 9:00 PM", "UTC", now=_mon(12)
        )
        assert r["status"] == "open"
        assert r["closes_at"] == "9:00 PM"

    def test_narrow_no_break_space_open(self) -> None:
        # U+202F before AM/PM, as emitted by Google Places weekday_text.
        text = "Monday: 9:00\u202fAM - 9:00\u202fPM"
        r = compute_store_status(None, text, "UTC", now=_mon(12))
        assert r["status"] == "open"
        assert r["closes_at"] == "9:00 PM"

    def test_bare_hour_open(self) -> None:
        r = compute_store_status(None, "Monday: 9 AM - 5 PM", "UTC", now=_mon(12))
        assert r["status"] == "open"
        assert r["closes_at"] == "5:00 PM"

    def test_closed_today(self) -> None:
        r = compute_store_status(None, "Monday: Closed", "UTC", now=_mon(12))
        assert r["status"] == "closed"
        assert r["source"] == "store_hours_text"

    def test_open_24_hours_null_close(self) -> None:
        r = compute_store_status(None, "Monday: Open 24 hours", "UTC", now=_mon(12))
        assert r["status"] == "open"
        assert r["is_open"] is True
        assert r["closes_at"] is None
        assert r["minutes_to_close"] is None

    def test_split_shift_open_in_first_range(self) -> None:
        text = "Monday: 11:00 AM - 2:00 PM, 5:00 PM - 10:00 PM"
        r = compute_store_status(None, text, "UTC", now=_mon(12))
        assert r["status"] == "open"
        assert r["closes_at"] == "2:00 PM"
        assert r["minutes_to_close"] == 120

    def test_split_shift_closed_in_gap(self) -> None:
        text = "Monday: 11:00 AM - 2:00 PM, 5:00 PM - 10:00 PM"
        r = compute_store_status(None, text, "UTC", now=_mon(15))
        assert r["status"] == "closed"
        assert r["opens_at"] == "5:00 PM"
        assert r["minutes_to_open"] == 120

    def test_split_shift_open_in_second_range(self) -> None:
        text = "Monday: 11:00 AM - 2:00 PM, 5:00 PM - 10:00 PM"
        r = compute_store_status(None, text, "UTC", now=_mon(18))
        assert r["status"] == "open"
        assert r["closes_at"] == "10:00 PM"
        assert r["minutes_to_close"] == 240

    def test_malformed_split_shift_unknown(self) -> None:
        text = "Monday: 11:00 AM - 2:00 PM, 17:00 - 22:00"
        r = compute_store_status(None, text, "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"

    def test_overnight_open_late(self) -> None:
        r = compute_store_status(None, "Monday: 8:00 PM - 2:00 AM", "UTC", now=_mon(23))
        assert r["status"] == "open"
        assert r["closes_at"] == "2:00 AM"
        assert r["minutes_to_close"] == 180

    def test_overnight_yesterday_spillover(self) -> None:
        text = "Sunday: 8:00 PM - 2:00 AM\nMonday: 8:00 PM - 2:00 AM"
        r = compute_store_status(None, text, "UTC", now=_mon(1))
        assert r["status"] == "open"
        assert r["closes_at"] == "2:00 AM"
        assert r["minutes_to_close"] == 60

    def test_next_open_across_days(self) -> None:
        text = "Monday: Closed\nTuesday: 9:00 AM - 5:00 PM"
        r = compute_store_status(None, text, "UTC", now=_mon(12))
        assert r["status"] == "closed"
        assert r["opens_at"] == "9:00 AM"
        assert r["minutes_to_open"] == 21 * 60

    def test_today_missing_unknown(self) -> None:
        r = compute_store_status(
            None, "Tuesday: 9:00 AM - 5:00 PM", "UTC", now=_mon(12)
        )
        assert r["status"] == "hours_unknown"

    def test_today_garbage_unknown(self) -> None:
        r = compute_store_status(None, "Monday: gibberish", "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"

    def test_grouped_days_unknown(self) -> None:
        r = compute_store_status(None, "Mon-Fri: 9 AM - 5 PM", "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"

    def test_empty_value_after_colon_unknown(self) -> None:
        r = compute_store_status(None, "Monday: ", "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"


class TestComputeStoreStatusContract:
    """Output-shape and mutual-exclusivity guarantees."""

    def test_exact_key_set(self) -> None:
        for r in (
            compute_store_status(_MON_9_22, None, "UTC", now=_mon(12)),
            compute_store_status(_MON_9_22, None, "UTC", now=_mon(6)),
            compute_store_status(None, None, "UTC", now=_mon(12)),
        ):
            assert set(r.keys()) == _EXPECTED_KEYS

    def test_status_enum_only(self) -> None:
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(12))
        assert r["status"] in {"open", "closed", "hours_unknown"}
        assert "closing_soon" not in r.values()

    def test_mutual_exclusivity_open(self) -> None:
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(12))
        assert r["opens_at"] is None and r["minutes_to_open"] is None

    def test_mutual_exclusivity_closed(self) -> None:
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(6))
        assert r["closes_at"] is None and r["minutes_to_close"] is None

    def test_mutual_exclusivity_unknown(self) -> None:
        r = compute_store_status(None, None, "UTC", now=_mon(12))
        assert r["closes_at"] is None and r["minutes_to_close"] is None
        assert r["opens_at"] is None and r["minutes_to_open"] is None
        assert r["source"] == "none"


class TestComputeStoreStatusSummary:
    """The factual, spoken-friendly summary line."""

    def test_open_far(self) -> None:
        # Thursday period (Google day 4 = Python Thursday); evaluated on Thu 2024-06-20.
        bh = _bh(
            [{"open": {"day": 4, "time": "0900"}, "close": {"day": 4, "time": "2130"}}]
        )
        r = compute_store_status(
            bh, None, "America/Toronto", now=datetime(2024, 6, 20, 22, 42, tzinfo=_UTC)
        )
        # 22:42 UTC == 18:42 (6:42 PM) Toronto on Thu 2024-06-20.
        assert r["summary"] == (
            "Store is OPEN now (Thu 6:42 PM, America/Toronto). " "Closes 9:30 PM."
        )

    def test_open_near_close_reads_open(self) -> None:
        bh = _bh(
            [{"open": {"day": 1, "time": "0900"}, "close": {"day": 1, "time": "2130"}}]
        )
        r = compute_store_status(bh, None, "UTC", now=_mon(21, 12))
        assert "OPEN" in r["summary"]
        assert r["summary"] == "Store is OPEN now (Mon 9:12 PM, UTC). Closes 9:30 PM."
        assert "closing soon" not in r["summary"].lower()

    def test_open_one_hour(self) -> None:
        bh = _bh(
            [{"open": {"day": 1, "time": "0900"}, "close": {"day": 1, "time": "1300"}}]
        )
        r = compute_store_status(bh, None, "UTC", now=_mon(12))
        assert r["summary"].endswith("Closes 1:00 PM.")

    def test_closed_with_next_open(self) -> None:
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(6))
        assert r["summary"] == (
            "Store is CLOSED now (Mon 6:00 AM, UTC). Opens 9:00 AM Monday."
        )

    def test_closed_next_open_over_24h_omits_duration(self) -> None:
        text = "Monday: Closed\nWednesday: 9:00 AM - 5:00 PM"
        r = compute_store_status(None, text, "UTC", now=_mon(12))
        assert (
            r["summary"]
            == "Store is CLOSED now (Mon 12:00 PM, UTC). Opens 9:00 AM Wednesday."
        )
        assert r["minutes_to_open"] is not None and r["minutes_to_open"] >= 24 * 60

    def test_closed_without_next_open(self) -> None:
        bh = _bh([{"open": {"time": "0900"}, "close": {"time": "2200"}}])
        r = compute_store_status(bh, None, "UTC", now=_mon(12))
        assert r["summary"] == "Store is CLOSED now (Mon 12:00 PM, UTC)."

    def test_hours_unknown(self) -> None:
        r = compute_store_status(None, None, "UTC", now=_mon(12))
        assert r["summary"] == (
            "Store hours could not be determined automatically; "
            "use the Store Hours listed in the prompt."
        )


class TestComputeStoreStatusSafety:
    """Hot-path safety: never raise."""

    def test_exception_returns_unknown(self, monkeypatch) -> None:
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "services.message_service._store_status.is_within_business_hours", boom
        )
        r = compute_store_status(_MON_9_22, None, "UTC", now=_mon(12))
        assert r["status"] == "hours_unknown"
        assert r["source"] == "none"

    def test_invalid_timezone_falls_back(self) -> None:
        # All-week 24h periods -> open; summary must show the fallback zone, no raise.
        periods = [
            {"open": {"day": d, "time": "0000"}, "close": {"day": d, "time": "2359"}}
            for d in range(7)
        ]
        r = compute_store_status(_bh(periods), None, "Invalid/Zone", now=_mon(12))
        assert r["status"] == "open"
        assert "America/Los_Angeles" in r["summary"]

    def test_garbage_timezone_does_not_raise(self) -> None:
        # An absolute-path string makes ZoneInfo raise ValueError (not
        # ZoneInfoNotFoundError); the broadened fallback must still not raise.
        # No hours data here, so the result is hours_unknown regardless of tz.
        r = compute_store_status(None, None, "/etc/localtime", now=_mon(12))
        assert r["status"] == "hours_unknown"

    def test_value_error_timezone_with_hours_reports_status(self) -> None:
        # With hours present, a ValueError-raising tz (absolute path) must NOT degrade
        # to hours_unknown: compute_store_status passes the already-validated tz_name
        # into Tier 1, so the engine resolves the default zone and reports real status.
        # (The engine alone catches only ZoneInfoNotFoundError, so passing the raw
        # string would let the ValueError escape Tier 1 — this guards that fix.)
        periods = [
            {"open": {"day": d, "time": "0000"}, "close": {"day": d, "time": "2359"}}
            for d in range(7)
        ]
        r = compute_store_status(_bh(periods), None, "/etc/localtime", now=_mon(12))
        assert r["status"] == "open"
        assert "America/Los_Angeles" in r["summary"]
