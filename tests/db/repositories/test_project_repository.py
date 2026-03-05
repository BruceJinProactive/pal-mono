"""Tests for ProjectRepository and ProjectRepositoryAsync.

Business focus: Channel routing (hot path for every inbound call/message),
business hours sync, project lifecycle with version checking, and location management.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db.repositories.project_repository import (
    ProjectRepository,
    ProjectRepositoryAsync,
    _format_special_hours,
    _format_time,
)
from db.tables import Project

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    mock_query = MagicMock()
    session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.params.return_value = mock_query
    return session


@pytest.fixture
def mock_async_session():
    return AsyncMock()


@pytest.fixture
def repo(mock_session):
    return ProjectRepository(mock_session)


@pytest.fixture
def repo_no_commit(mock_session):
    return ProjectRepository(mock_session, auto_commit=False)


@pytest.fixture
def async_repo(mock_async_session):
    return ProjectRepositoryAsync(mock_async_session)


@pytest.fixture
def sample_project_id():
    return uuid.uuid4()


@pytest.fixture
def sample_account_id():
    return uuid.uuid4()


@pytest.fixture
def sample_project(sample_project_id, sample_account_id):
    project = MagicMock(spec=Project)
    project.id = sample_project_id
    project.account_id = sample_account_id
    project.name = "test-store"
    project.channel_identifiers = ["voice:+15551234567", "sms:+15551234567"]
    project.raw_config = {"channels": []}
    project.google_place_id = "ChIJ_test"
    project.business_hours_last_updated = None
    project.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return project


# ---------------------------------------------------------------------------
# TestProjectChannelRoutingAsync — Hot path for every inbound call
# ---------------------------------------------------------------------------


class TestProjectChannelRoutingAsync:
    """Every inbound call/SMS must route to the correct restaurant location.
    This is the most performance-critical lookup in the system."""

    @pytest.mark.asyncio
    async def test_get_project_by_channel_identifier_found(
        self, async_repo, mock_async_session, sample_project
    ):
        """Incoming call routes to correct restaurant."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_project_by_channel_identifier(
            "voice:+15551234567"
        )
        assert result == sample_project

    @pytest.mark.asyncio
    async def test_get_project_by_channel_identifier_not_found(
        self, async_repo, mock_async_session
    ):
        """Unknown phone number returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_project_by_channel_identifier(
            "voice:+19999999999"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_async_get_project_by_id(
        self, async_repo, mock_async_session, sample_project
    ):
        """Async ID lookup."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_project(sample_project.id)
        assert result == sample_project

    @pytest.mark.asyncio
    async def test_async_get_project_by_id_not_found(
        self, async_repo, mock_async_session
    ):
        """Nonexistent project returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_project(uuid.uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# TestProjectChannelRoutingSync
# ---------------------------------------------------------------------------


class TestProjectChannelRoutingSync:
    """Sync channel routing used in non-async paths."""

    def test_get_project_by_channel_identifier(
        self, repo, mock_session, sample_project
    ):
        """Sync channel identifier lookup."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        result = repo.get_project_by_channel_identifier("voice:+15551234567")
        assert result == sample_project

    def test_get_project_by_channel_identifier_not_found(self, repo, mock_session):
        """Unknown identifier returns None."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = repo.get_project_by_channel_identifier("voice:+19999999999")
        assert result is None

    def test_get_projects_by_phone_number(self, repo, mock_session, sample_project):
        """Phone number matched across voice:/sms:/phone: prefixes."""
        mock_session.query.return_value.filter.return_value.params.return_value.all.return_value = [
            sample_project
        ]
        result = repo.get_projects_by_phone_number("+15551234567")
        assert result == [sample_project]

    def test_get_projects_by_phone_number_returns_empty_for_unknown(
        self, repo, mock_session
    ):
        """No match returns empty list."""
        mock_session.query.return_value.filter.return_value.params.return_value.all.return_value = (
            []
        )
        result = repo.get_projects_by_phone_number("+19999999999")
        assert result == []

    def test_get_project_by_channel_platform_and_identifier(
        self, repo, mock_session, sample_project
    ):
        """JSONB channel config lookup."""
        mock_session.query.return_value.filter.return_value.params.return_value.first.return_value = (
            sample_project
        )
        result = repo.get_project_by_channel("sms", "+15551234567")
        assert result == sample_project

    def test_get_project_by_channel_raises_on_missing_platform(self, repo):
        """Input validation: platform required."""
        with pytest.raises(ValueError, match="channel_platform"):
            repo.get_project_by_channel("", "+15551234567")

    def test_get_project_by_channel_raises_on_missing_identifier(self, repo):
        """Input validation: identifier required."""
        with pytest.raises(ValueError, match="channel_identifier"):
            repo.get_project_by_channel("sms", "")


# ---------------------------------------------------------------------------
# TestProjectCreation
# ---------------------------------------------------------------------------


class TestProjectCreation:
    """New restaurant location onboarding."""

    def test_create_project_success(self, repo, mock_session, sample_account_id):
        """New restaurant location added."""
        result = repo.create_project(sample_account_id, "new-store")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert isinstance(result, Project)

    def test_create_project_with_kwargs(self, repo, mock_session, sample_account_id):
        """Additional config set during creation."""
        result = repo.create_project(
            sample_account_id,
            "new-store",
            display_name="New Store",
            google_place_id="ChIJ_new",
        )
        assert isinstance(result, Project)

    def test_create_project_integrity_error_raises_value_error(
        self, repo, mock_session, sample_account_id
    ):
        """Duplicate project name raises clean error."""
        mock_session.commit.side_effect = IntegrityError(
            "duplicate key", {}, Exception()
        )
        with pytest.raises(ValueError, match="Error creating project"):
            repo.create_project(sample_account_id, "duplicate-store")
        mock_session.rollback.assert_called_once()

    def test_create_project_db_error_rolls_back(
        self, repo, mock_session, sample_account_id
    ):
        """Generic DB error rolls back and re-raises."""
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")
        with pytest.raises(SQLAlchemyError):
            repo.create_project(sample_account_id, "new-store")
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_create_project_success(
        self, async_repo, mock_async_session, sample_account_id
    ):
        """Async project creation."""
        result = await async_repo.create_project(sample_account_id, "new-store")
        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_awaited_once()
        assert isinstance(result, Project)

    @pytest.mark.asyncio
    async def test_async_create_project_integrity_error(
        self, async_repo, mock_async_session, sample_account_id
    ):
        """Async path: duplicate raises ValueError."""
        mock_async_session.commit.side_effect = IntegrityError(
            "duplicate key", {}, Exception()
        )
        with pytest.raises(ValueError, match="Error creating project"):
            await async_repo.create_project(sample_account_id, "duplicate-store")
        mock_async_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestProjectUpdate — Settings changes with version checking
# ---------------------------------------------------------------------------


class TestProjectUpdate:
    """Project settings changes. Version checking prevents concurrent edits."""

    def test_update_project_success(self, repo, mock_session, sample_project):
        """Update restaurant settings."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        result = repo.update_project(sample_project.id, display_name="Updated Store")
        assert result == sample_project
        mock_session.commit.assert_called_once()

    def test_update_project_version_mismatch_raises(
        self, repo, mock_session, sample_project
    ):
        """Concurrent edit detection."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        wrong_version = int(sample_project.updated_at.timestamp()) + 100
        with pytest.raises(ValueError, match="Version mismatch"):
            repo.update_project(
                sample_project.id,
                expected_version=wrong_version,
                display_name="Overwrite",
            )

    def test_update_project_not_found_returns_none(self, repo, mock_session):
        """Nonexistent project handled."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = repo.update_project(uuid.uuid4(), display_name="X")
        assert result is None

    def test_update_project_skips_none_values(self, repo, mock_session, sample_project):
        """None values in kwargs should not overwrite existing fields."""
        original_display_name = "Original Name"
        sample_project.display_name = original_display_name
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        # Try to update with None value - should be skipped
        result = repo.update_project(sample_project.id, display_name=None)
        assert result == sample_project
        # Verify the original value wasn't cleared
        assert sample_project.display_name == original_display_name
        mock_session.commit.assert_called_once()

    def test_update_project_config_partial_update(
        self, repo, mock_session, sample_project
    ):
        """Update specific config keys without replacing all."""
        mock_config = MagicMock()
        sample_project.raw_config = mock_config
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        repo.update_project_config(sample_project.id, {"new_key": "new_value"})
        mock_config.update.assert_called_once_with({"new_key": "new_value"})

    def test_update_project_config_not_found_raises(self, repo, mock_session):
        """Missing project raises ValueError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            repo.update_project_config(uuid.uuid4(), {"key": "value"})

    def test_replace_project_config(self, repo, mock_session, sample_project):
        """Full config replacement."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        new_config = {"channels": [{"platform": "sms", "identifier": "+15551111111"}]}
        repo.replace_project_config(sample_project.id, new_config)
        assert sample_project.raw_config == new_config

    def test_replace_project_config_not_found_raises(self, repo, mock_session):
        """Missing project raises ValueError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            repo.replace_project_config(uuid.uuid4(), {"channels": []})

    def test_replace_channel_identifiers(self, repo, mock_session, sample_project):
        """Phone number assignment change."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        new_ids = ["voice:+15559999999"]
        repo.replace_project_channel_identifiers(sample_project.id, new_ids)
        assert sample_project.channel_identifiers == new_ids

    def test_replace_channel_identifiers_not_found_raises(self, repo, mock_session):
        """Missing project raises ValueError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            repo.replace_project_channel_identifiers(uuid.uuid4(), ["voice:+15551111"])


# ---------------------------------------------------------------------------
# TestProjectBusinessHours — Automated Google hours sync
# ---------------------------------------------------------------------------


class TestProjectBusinessHours:
    """Business hours management for agent context. The sync job finds stale
    hours and updates them from Google Places data."""

    def test_get_projects_needing_hours_update(
        self, repo, mock_session, sample_project
    ):
        """Cron job finds stale business hours."""
        mock_q = mock_session.query.return_value
        mock_q.options.return_value.filter.return_value.all.return_value = [
            sample_project
        ]
        result = repo.get_projects_needing_hours_update()
        assert result == [sample_project]

    def test_get_projects_needing_hours_update_returns_empty_on_error(
        self, repo, mock_session
    ):
        """Error resilience for cron job."""
        mock_session.query.side_effect = SQLAlchemyError("error")
        result = repo.get_projects_needing_hours_update()
        assert result == []

    def test_update_business_hours_sets_store_hours_text(
        self, repo, mock_session, sample_project
    ):
        """Google Places data formatted for agent context."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        business_hours = {
            "regular_hours": {
                "weekday_text": [
                    "Monday: 9:00 AM – 5:00 PM",
                    "Tuesday: 9:00 AM – 5:00 PM",
                ]
            }
        }
        repo.update_project_business_hours(
            sample_project.id, business_hours, datetime.now(timezone.utc)
        )
        assert sample_project.business_hours == business_hours
        assert "Monday" in sample_project.store_hours

    def test_update_business_hours_includes_special_hours(
        self, repo, mock_session, sample_project
    ):
        """Holiday hours appended to display text."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        business_hours = {
            "regular_hours": {"weekday_text": ["Monday: 9:00 AM – 5:00 PM"]},
            "special_hours": [
                {
                    "date": "2025-12-25",
                    "exceptional_hours": True,
                    "periods": [],
                }
            ],
        }
        repo.update_project_business_hours(
            sample_project.id, business_hours, datetime.now(timezone.utc)
        )
        assert "Special Hours" in sample_project.store_hours
        assert "Closed" in sample_project.store_hours

    def test_update_business_hours_not_found_raises(self, repo, mock_session):
        """Missing project raises ValueError."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            repo.update_project_business_hours(uuid.uuid4(), {}, datetime.now())

    def test_get_projects_with_google_place_id(
        self, repo, mock_session, sample_project
    ):
        """Only projects with Google integration."""
        mock_q = mock_session.query.return_value
        mock_q.options.return_value.filter.return_value.all.return_value = [
            sample_project
        ]
        result = repo.get_projects_with_google_place_id()
        assert result == [sample_project]

    def test_get_projects_with_google_place_id_returns_empty_on_error(
        self, repo, mock_session
    ):
        """Error resilience."""
        mock_session.query.side_effect = SQLAlchemyError("error")
        result = repo.get_projects_with_google_place_id()
        assert result == []


# ---------------------------------------------------------------------------
# TestProjectDeletion
# ---------------------------------------------------------------------------


class TestProjectDeletion:
    """Restaurant location removal."""

    def test_delete_project_success(self, repo, mock_session, sample_project):
        """Remove a restaurant location."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        repo.delete_project(sample_project.id)
        mock_session.delete.assert_called_once_with(sample_project)
        mock_session.commit.assert_called_once()

    def test_delete_nonexistent_project_is_noop(self, repo, mock_session):
        """Idempotent deletion."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        repo.delete_project(uuid.uuid4())
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_delete_project(
        self, async_repo, mock_async_session, sample_project
    ):
        """Async variant."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_async_session.execute.return_value = mock_result

        await async_repo.delete_project(sample_project.id)
        mock_async_session.delete.assert_awaited_once_with(sample_project)
        mock_async_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestProjectQueries — Additional lookups
# ---------------------------------------------------------------------------


class TestProjectQueries:
    """Additional project lookup methods."""

    def test_get_project_by_id(self, repo, mock_session, sample_project):
        """Direct ID lookup."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        result = repo.get_project(sample_project.id)
        assert result == sample_project

    def test_get_project_by_name(self, repo, mock_session, sample_project):
        """Name-based lookup."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_project
        )
        result = repo.get_project_by_name("test-store")
        assert result == sample_project

    def test_get_projects_by_account_id(self, repo, mock_session, sample_project):
        """List all locations for a restaurant."""
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            sample_project
        ]
        result = repo.get_projects_by_account_id(sample_project.account_id)
        assert result == [sample_project]

    def test_get_projects_by_ids(self, repo, mock_session, sample_project):
        """Batch lookup by IDs."""
        mock_session.query.return_value.filter.return_value.all.return_value = [
            sample_project
        ]
        result = repo.get_projects_by_ids([sample_project.id])
        assert result == [sample_project]

    def test_get_projects_by_ids_empty_list_returns_empty(self, repo, mock_session):
        """Empty ID list returns empty without DB query."""
        result = repo.get_projects_by_ids([])
        assert result == []
        mock_session.query.assert_not_called()

    def test_get_projects_by_ids_returns_empty_on_error(self, repo, mock_session):
        """Error resilience for batch lookup."""
        mock_session.query.return_value.filter.return_value.all.side_effect = (
            SQLAlchemyError("error")
        )
        result = repo.get_projects_by_ids([uuid.uuid4()])
        assert result == []


# ---------------------------------------------------------------------------
# TestFormatHelpers — Business hours formatting utilities
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    """Helper functions for formatting Google Places hours data."""

    def test_format_time_standard(self):
        """Standard time formatting."""
        assert _format_time("0900") == "9:00 AM"
        assert _format_time("1200") == "12:00 PM"
        assert _format_time("1730") == "5:30 PM"
        assert _format_time("0000") == "12:00 AM"

    def test_format_time_invalid_input(self):
        """Invalid input returned as-is."""
        assert _format_time("") == ""
        assert _format_time("abc") == "abc"
        assert _format_time("999") == "999"
        assert _format_time("2500") == "2500"

    def test_format_special_hours_closed_day(self):
        """Holiday with no periods = closed."""
        special = [{"date": "2025-12-25", "exceptional_hours": True, "periods": []}]
        result = _format_special_hours(special)
        assert len(result) == 1
        assert "Closed" in result[0]
        assert "Holiday Hours" in result[0]

    def test_format_special_hours_with_times(self):
        """Holiday with reduced hours."""
        special = [
            {
                "date": "2025-12-25",
                "exceptional_hours": True,
                "periods": [{"open": {"time": "1200"}, "close": {"time": "1600"}}],
            }
        ]
        result = _format_special_hours(special)
        assert len(result) == 1
        assert "12:00 PM" in result[0]
        assert "4:00 PM" in result[0]

    def test_format_special_hours_skips_missing_date(self):
        """Entries without date are skipped."""
        special = [{"exceptional_hours": True, "periods": []}]
        result = _format_special_hours(special)
        assert result == []
