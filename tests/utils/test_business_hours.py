"""Tests for the business-hours engine (utils.business_hours)."""

from datetime import date, datetime, time, timezone

from utils.business_hours import (
    _check_regular_hours,
    _check_special_hours,
    is_within_business_hours,
    parse_google_time,
)


class TestParseTime:
    """Tests for parse_google_time — parsing Google Places HHMM format."""

    def test_valid_morning(self) -> None:
        """Should parse '0900' to time(9, 0)."""
        assert parse_google_time("0900") == time(9, 0)

    def test_valid_evening(self) -> None:
        """Should parse '2200' to time(22, 0)."""
        assert parse_google_time("2200") == time(22, 0)

    def test_empty_string_returns_midnight(self) -> None:
        """Should return time(0, 0) for empty string."""
        assert parse_google_time("") == time(0, 0)

    def test_invalid_length_returns_midnight(self) -> None:
        """Should return time(0, 0) for string with wrong length."""
        assert parse_google_time("12") == time(0, 0)

    def test_non_numeric_returns_midnight(self) -> None:
        """Should return time(0, 0) for non-numeric input."""
        assert parse_google_time("abcd") == time(0, 0)


class TestCheckSpecialHours:
    """Tests for _check_special_hours — holiday/closure handling."""

    def test_closed_day_no_periods(self) -> None:
        """Should return is_open=False for special day with no periods (closure)."""
        special_hours = [{"date": "2024-12-25", "periods": []}]
        result = _check_special_hours(date(2024, 12, 25), time(10, 0), special_hours)
        assert result is not None
        assert result.is_open is False
        assert result.reason == "special_closure"

    def test_within_special_period(self) -> None:
        """Should return is_open=True when time is within a special hours period."""
        special_hours = [
            {
                "date": "2024-12-24",
                "periods": [
                    {
                        "open": {"time": "0900"},
                        "close": {"time": "1400"},
                    }
                ],
            }
        ]
        result = _check_special_hours(date(2024, 12, 24), time(11, 0), special_hours)
        assert result is not None
        assert result.is_open is True
        assert result.reason == "within_special_hours"

    def test_outside_special_period_on_special_day(self) -> None:
        """Should return is_open=False when outside all periods on a special day."""
        special_hours = [
            {
                "date": "2024-12-24",
                "periods": [
                    {
                        "open": {"time": "0900"},
                        "close": {"time": "1400"},
                    }
                ],
            }
        ]
        result = _check_special_hours(date(2024, 12, 24), time(16, 0), special_hours)
        assert result is not None
        assert result.is_open is False
        assert result.reason == "outside_special_hours"

    def test_overnight_special_hours_opening_day(self) -> None:
        """Should return is_open=True for overnight special hours on opening day."""
        special_hours = [
            {
                "date": "2024-12-31",
                "periods": [
                    {
                        "open": {"time": "2200"},
                        "close": {"time": "0200"},
                    }
                ],
            }
        ]
        # On the opening day, after open time
        result = _check_special_hours(date(2024, 12, 31), time(23, 0), special_hours)
        assert result is not None
        assert result.is_open is True
        assert result.reason == "within_special_hours_overnight"

    def test_overnight_special_hours_closing_day(self) -> None:
        """Should return is_open=True for overnight special hours on closing day (next day)."""
        special_hours = [
            {
                "date": "2024-12-31",
                "periods": [
                    {
                        "open": {"time": "2200"},
                        "close": {"time": "0200"},
                    }
                ],
            }
        ]
        # On the closing day (Jan 1), before close time
        result = _check_special_hours(date(2025, 1, 1), time(1, 0), special_hours)
        assert result is not None
        assert result.is_open is True
        assert result.reason == "within_special_hours_overnight"

    def test_non_matching_date_returns_none(self) -> None:
        """Should return None when no special hours match the date."""
        special_hours = [{"date": "2024-12-25", "periods": []}]
        result = _check_special_hours(date(2024, 6, 15), time(10, 0), special_hours)
        assert result is None

    def test_invalid_date_format_skipped(self) -> None:
        """Should skip entries with invalid date format and return None."""
        special_hours = [{"date": "not-a-date", "periods": []}]
        result = _check_special_hours(date(2024, 6, 15), time(10, 0), special_hours)
        assert result is None


class TestCheckRegularHours:
    """Tests for _check_regular_hours — weekly schedule checking."""

    def test_same_day_inside(self) -> None:
        """Should return is_open=True when within a same-day period."""
        periods = [
            {
                "open": {"day": 1, "time": "0900"},
                "close": {"day": 1, "time": "2200"},
            }
        ]
        result = _check_regular_hours(1, time(12, 0), periods)
        assert result.is_open is True
        assert result.reason == "within_regular_hours"

    def test_same_day_outside(self) -> None:
        """Should return is_open=False when outside all same-day periods."""
        periods = [
            {
                "open": {"day": 1, "time": "0900"},
                "close": {"day": 1, "time": "2200"},
            }
        ]
        result = _check_regular_hours(1, time(23, 0), periods)
        assert result.is_open is False
        assert result.reason == "outside_regular_hours"

    def test_same_day_at_boundary(self) -> None:
        """Should return is_open=True at period boundary (inclusive)."""
        periods = [
            {
                "open": {"day": 1, "time": "0900"},
                "close": {"day": 1, "time": "2200"},
            }
        ]
        result = _check_regular_hours(1, time(9, 0), periods)
        assert result.is_open is True

    def test_overnight_on_opening_day(self) -> None:
        """Should return is_open=True on opening day of overnight period."""
        # Friday 22:00 - Saturday 02:00 (Friday=6, Saturday=0 in Google format)
        periods = [
            {
                "open": {"day": 6, "time": "2200"},
                "close": {"day": 0, "time": "0200"},
            }
        ]
        result = _check_regular_hours(6, time(23, 0), periods)
        assert result.is_open is True
        assert result.reason == "within_overnight_hours"

    def test_overnight_on_closing_day_after_midnight(self) -> None:
        """Should return is_open=True on closing day of overnight period after midnight."""
        # Friday 22:00 - Saturday 02:00 (Friday=6, Saturday=0 in Google format)
        periods = [
            {
                "open": {"day": 6, "time": "2200"},
                "close": {"day": 0, "time": "0200"},
            }
        ]
        result = _check_regular_hours(0, time(1, 0), periods)
        assert result.is_open is True
        assert result.reason == "within_overnight_hours"

    def test_no_matching_period(self) -> None:
        """Should return outside_regular_hours when no period matches."""
        periods = [
            {
                "open": {"day": 1, "time": "0900"},
                "close": {"day": 1, "time": "2200"},
            }
        ]
        # Day 3 (Wednesday) has no period
        result = _check_regular_hours(3, time(12, 0), periods)
        assert result.is_open is False
        assert result.reason == "outside_regular_hours"


class TestIsWithinBusinessHours:
    """Tests for is_within_business_hours — main entry point."""

    def test_no_business_hours_data(self) -> None:
        """Should return is_open=True when no business_hours data provided."""
        result = is_within_business_hours(
            captured_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            business_hours=None,
            timezone_str="America/Los_Angeles",
        )
        assert result.is_open is True
        assert result.reason == "no_business_hours_data"

    def test_invalid_timezone_falls_back(self) -> None:
        """Should fall back to America/Los_Angeles for invalid timezone."""
        business_hours = {
            "regular_hours": {
                "periods": [
                    {
                        "open": {"day": 0, "time": "0000"},
                        "close": {"day": 0, "time": "2359"},
                    },
                    {
                        "open": {"day": 1, "time": "0000"},
                        "close": {"day": 1, "time": "2359"},
                    },
                    {
                        "open": {"day": 2, "time": "0000"},
                        "close": {"day": 2, "time": "2359"},
                    },
                    {
                        "open": {"day": 3, "time": "0000"},
                        "close": {"day": 3, "time": "2359"},
                    },
                    {
                        "open": {"day": 4, "time": "0000"},
                        "close": {"day": 4, "time": "2359"},
                    },
                    {
                        "open": {"day": 5, "time": "0000"},
                        "close": {"day": 5, "time": "2359"},
                    },
                    {
                        "open": {"day": 6, "time": "0000"},
                        "close": {"day": 6, "time": "2359"},
                    },
                ]
            }
        }
        # Should not raise, should use fallback timezone
        result = is_within_business_hours(
            captured_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            business_hours=business_hours,
            timezone_str="Invalid/Timezone",
        )
        assert result.is_open is True

    def test_naive_datetime_treated_as_utc(self) -> None:
        """Should treat naive datetime as UTC."""
        # Monday 12:00 UTC
        captured_at = datetime(2024, 6, 17, 12, 0, 0)  # naive - no tzinfo
        business_hours = {
            "regular_hours": {
                "periods": [
                    {
                        # Monday in Google format = 1
                        "open": {"day": 1, "time": "0000"},
                        "close": {"day": 1, "time": "2359"},
                    }
                ]
            }
        }
        result = is_within_business_hours(
            captured_at=captured_at,
            business_hours=business_hours,
            timezone_str="UTC",
        )
        assert result.is_open is True

    def test_special_hours_checked_before_regular(self) -> None:
        """Should check special hours before regular hours."""
        # Special hours say closed, but regular hours say open
        captured_at = datetime(2024, 12, 25, 12, 0, 0, tzinfo=timezone.utc)
        business_hours = {
            "special_hours": [
                {"date": "2024-12-25", "periods": []}  # Closed for Christmas
            ],
            "regular_hours": {
                "periods": [
                    {
                        # Wednesday in Google format = 4
                        "open": {"day": 4, "time": "0900"},
                        "close": {"day": 4, "time": "2200"},
                    }
                ]
            },
        }
        result = is_within_business_hours(
            captured_at=captured_at,
            business_hours=business_hours,
            timezone_str="UTC",
        )
        assert result.is_open is False
        assert result.reason == "special_closure"

    def test_no_periods_defined(self) -> None:
        """Should return is_open=True when no periods are defined."""
        result = is_within_business_hours(
            captured_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            business_hours={"regular_hours": {"periods": []}},
            timezone_str="UTC",
        )
        assert result.is_open is True
        assert result.reason == "no_periods_defined"

    def test_weekday_conversion(self) -> None:
        """Should correctly convert Python weekday to Google format."""
        # 2024-06-16 is a Sunday. Python weekday = 6, Google format = 0
        captured_at = datetime(2024, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
        business_hours = {
            "regular_hours": {
                "periods": [
                    {
                        "open": {"day": 0, "time": "0900"},  # Sunday in Google
                        "close": {"day": 0, "time": "2200"},
                    }
                ]
            }
        }
        result = is_within_business_hours(
            captured_at=captured_at,
            business_hours=business_hours,
            timezone_str="UTC",
        )
        assert result.is_open is True
        assert result.reason == "within_regular_hours"
