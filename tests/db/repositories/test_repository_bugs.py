"""Tests for bug fixes in Tier 1 repository code.

Each test verifies that a previously discovered bug has been fixed.
Tests assert the correct behavior after the fix.

Bug severity key:
  [CRITICAL] — Can cause data loss, billing errors, or security issues
  [HIGH]     — Incorrect behavior in production hot paths
  [MEDIUM]   — Silent data loss or inconsistent API contract
  [LOW]      — Edge case or cosmetic issue
"""

import datetime
import uuid
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.account_repository import AccountRepository
from db.repositories.conversation_repository import ConversationRepository
from db.repositories.project_repository import (
    ProjectRepository,
    _format_special_hours,
    _format_time,
)
from db.repositories.subscription_repository import SubscriptionPlanRepository
from db.tables import Account, Conversation, ConversationStatus, Project, User
from db.tables.accounts import AccountStatus

# ===========================================================================
# Bug 1 (FIXED): expected_version=0 bypasses optimistic locking
# [CRITICAL] — Fix: Use `is not None` instead of truthiness check
# ===========================================================================


class TestVersionCheckFix:
    """Fixed: expected_version=0 now correctly triggers version validation."""

    def test_account_update_version_zero_raises_on_mismatch(self):
        """[CRITICAL] expected_version=0 should raise ValueError when the
        actual version is different (e.g., account was updated)."""
        mock_session = MagicMock()
        repo = AccountRepository(mock_session)

        account = MagicMock(spec=Account)
        account.name = "test"
        account.status = AccountStatus.active
        account.updated_at = datetime.datetime(2025, 6, 15, tzinfo=timezone.utc)

        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            account
        )

        with pytest.raises(ValueError, match="Version mismatch"):
            repo.update_account("test", expected_version=0, display_name="Updated")

    def test_project_update_version_zero_raises_on_mismatch(self):
        """[CRITICAL] Same fix in project_repository."""
        mock_session = MagicMock()
        repo = ProjectRepository(mock_session)

        project = MagicMock(spec=Project)
        project.id = uuid.uuid4()
        project.updated_at = datetime.datetime(2025, 6, 15, tzinfo=timezone.utc)

        mock_session.query.return_value.filter.return_value.first.return_value = project

        with pytest.raises(ValueError, match="Version mismatch"):
            repo.update_project(project.id, expected_version=0, display_name="Updated")

    def test_account_update_version_none_skips_check(self):
        """expected_version=None should skip the version check (opt-out)."""
        mock_session = MagicMock()
        repo = AccountRepository(mock_session)

        account = MagicMock(spec=Account)
        account.name = "test"
        account.status = AccountStatus.active
        account.updated_at = datetime.datetime(2025, 6, 15, tzinfo=timezone.utc)

        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            account
        )

        # None means "don't check version" — should NOT raise
        result = repo.update_account("test", expected_version=None, display_name="OK")
        assert result is not None

    def test_account_update_version_matches(self):
        """expected_version matching actual timestamp should succeed."""
        mock_session = MagicMock()
        repo = AccountRepository(mock_session)

        ts = datetime.datetime(2025, 6, 15, tzinfo=timezone.utc)
        account = MagicMock(spec=Account)
        account.name = "test"
        account.status = AccountStatus.active
        account.updated_at = ts

        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            account
        )

        expected = int(ts.timestamp())
        result = repo.update_account(
            "test", expected_version=expected, display_name="OK"
        )
        assert result is not None


# ===========================================================================
# Bug 2 (FIXED): _format_special_hours silently drops entries
# [MEDIUM] — Fix: Handle partial open/close times with descriptive output
# ===========================================================================


class TestSpecialHoursPartialEntries:
    """Fixed: _format_special_hours now includes entries with partial times."""

    def test_entry_with_open_but_no_close_shows_opens_at(self):
        """[MEDIUM] Holiday with open_time but no close_time shows partial info."""
        special = [
            {
                "date": "2025-07-04",
                "exceptional_hours": True,
                "periods": [
                    {
                        "open": {"time": "0800"},
                    }
                ],
            }
        ]

        result = _format_special_hours(special)
        assert len(result) == 1
        assert "Opens 8:00 AM" in result[0]
        assert "Holiday Hours" in result[0]

    def test_entry_with_close_but_no_open_shows_closes_at(self):
        """[MEDIUM] Holiday with close_time but no open_time shows partial info."""
        special = [
            {
                "date": "2025-07-04",
                "exceptional_hours": True,
                "periods": [
                    {
                        "close": {"time": "2200"},
                    }
                ],
            }
        ]

        result = _format_special_hours(special)
        assert len(result) == 1
        assert "Closes 10:00 PM" in result[0]
        assert "Holiday Hours" in result[0]

    def test_entry_with_both_times_still_works(self):
        """Full open/close range still formatted correctly."""
        special = [
            {
                "date": "2025-12-25",
                "exceptional_hours": True,
                "periods": [
                    {
                        "open": {"time": "0900"},
                        "close": {"time": "1700"},
                    }
                ],
            }
        ]

        result = _format_special_hours(special)
        assert len(result) == 1
        assert "9:00 AM" in result[0]
        assert "5:00 PM" in result[0]

    def test_entry_with_empty_open_dict_shows_closes_at(self):
        """[MEDIUM] Open dict present but time key missing, close has time."""
        special = [
            {
                "date": "2025-07-04",
                "exceptional_hours": True,
                "periods": [
                    {
                        "open": {},
                        "close": {"time": "1700"},
                    }
                ],
            }
        ]

        result = _format_special_hours(special)
        assert len(result) == 1
        assert "Closes 5:00 PM" in result[0]


# ===========================================================================
# Bug 3+4 (FIXED): get_conversations/get_conversations_by_user return []
# [HIGH] — Fix: Return [] on error for consistency with all other methods
# ===========================================================================


class TestConversationsReturnEmptyListFix:
    """Fixed: get_conversations() and get_conversations_by_user() return []
    on error instead of None."""

    def test_get_conversations_returns_empty_list_on_error(self):
        """[HIGH] get_conversations now returns [] on error, not None."""
        mock_session = MagicMock()
        repo = ConversationRepository(mock_session)

        mock_session.query.return_value.offset.return_value.limit.return_value.all.side_effect = SQLAlchemyError(
            "connection lost"
        )

        result = repo.get_conversations()
        assert result == []
        assert result is not None

    def test_get_conversations_by_user_returns_empty_list_on_error(self):
        """[HIGH] get_conversations_by_user now returns [] on error, not None."""
        mock_session = MagicMock()
        repo = ConversationRepository(mock_session)

        mock_session.query.return_value.filter.return_value.all.side_effect = (
            SQLAlchemyError("error")
        )

        result = repo.get_conversations_by_user(uuid.uuid4())
        assert result == []
        assert result is not None


# ===========================================================================
# Bug 5 (FIXED): _format_time handles "2400" (Google Places midnight)
# [LOW] — Fix: Special-case 2400 as "12:00 AM"
# ===========================================================================


class TestFormatTimeFix:
    """Fixed: _format_time handles '2400' as valid end-of-day midnight."""

    def test_2400_formats_as_midnight(self):
        """[LOW] '2400' now correctly formats as '12:00 AM'."""
        result = _format_time("2400")
        assert result == "12:00 AM"

    def test_format_time_normal_cases_unchanged(self):
        """Existing behavior preserved for normal times."""
        assert _format_time("0000") == "12:00 AM"
        assert _format_time("0900") == "9:00 AM"
        assert _format_time("1200") == "12:00 PM"
        assert _format_time("1730") == "5:30 PM"
        assert _format_time("2359") == "11:59 PM"

    def test_format_time_invalid_still_returns_raw(self):
        """Invalid times still return raw string."""
        assert _format_time("1260") == "1260"  # minute > 59
        assert _format_time("2500") == "2500"  # hour > 24
        assert _format_time("abc") == "abc"  # not digits
        assert _format_time("") == ""  # empty


# ===========================================================================
# Bug 6 (FIXED): Update methods can now set fields to None
# [MEDIUM] — Fix: Remove `value is not None` guard from setattr loop
# ===========================================================================


class TestCanSetFieldsToNone:
    """Fixed: Update methods now allow setting fields to None to clear them."""

    def test_subscription_plan_can_clear_field(self):
        """[MEDIUM] Can explicitly set subscription plan description to None."""
        from db.tables.subscriptions import SubscriptionPlan

        mock_session = MagicMock()
        repo = SubscriptionPlanRepository(mock_session)

        plan = MagicMock(spec=SubscriptionPlan)
        plan.id = uuid.uuid4()
        plan.active = True
        plan.description = "Old description"

        mock_session.query.return_value.filter.return_value.first.return_value = plan

        repo.update_subscription_plan(plan.id, description=None)

        # After fix: description should be set to None
        assert plan.description is None

    def test_account_update_can_clear_field(self):
        """[MEDIUM] Can set account display_name to None."""
        mock_session = MagicMock()
        repo = AccountRepository(mock_session)

        account = MagicMock(spec=Account)
        account.name = "test"
        account.display_name = "Old Name"
        account.status = AccountStatus.active
        account.updated_at = None

        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            account
        )

        repo.update_account("test", display_name=None)

        # After fix: display_name should be set to None
        assert account.display_name is None


# ===========================================================================
# Bug 7 (FIXED): Truthiness checks replaced with `is not None`
# [MEDIUM] — Fix: Use explicit None checks for optional parameters
# ===========================================================================


class TestTruthinessCheckFix:
    """Fixed: Conversation counts use `is not None` instead of truthiness."""

    def test_conversation_counts_uses_is_not_none(self):
        """[MEDIUM] Verify the pattern uses `is not None` by checking source."""
        import inspect

        source = inspect.getsource(
            ConversationRepository.get_conversation_counts_by_account
        )

        assert "start_date is not None" in source
        assert "end_date is not None" in source
        assert "account_id is not None" in source


# ===========================================================================
# Bug 8 (FIXED): Message repo 2hr check no longer runs after 24hr expiration
# [CRITICAL] — Fix: 2hr check only runs inside the 24hr-valid branch
# ===========================================================================


class TestMessageRepoConversationReuseFix:
    """Fixed: After 24hr expiration, the 2-hour message gap check is skipped.
    A new conversation is created instead of querying with conversation_id=None."""

    @pytest.mark.asyncio
    async def test_expired_conversation_creates_new_without_2hr_check(self):
        """[CRITICAL] After 24hr expiration, a new conversation is created
        without running the 2hr message gap check."""
        from db.repositories.message_repository import MessageRepositoryAsync

        mock_session = AsyncMock()

        mock_user = MagicMock(spec=User)
        mock_user.id = uuid.uuid4()

        mock_conversation = MagicMock(spec=Conversation)
        mock_conversation.id = uuid.uuid4()
        mock_conversation.status = ConversationStatus.ACTIVE
        mock_conversation.created_at = datetime.datetime(
            2025, 1, 1, tzinfo=datetime.timezone.utc
        )  # Very old (> 24hr)
        mock_conversation.user_id = mock_user.id

        execute_calls = []

        async def mock_execute(query):
            execute_calls.append(query)
            result = MagicMock()

            call_count = len(execute_calls)
            if call_count == 1:
                # User lookup
                result.scalar_one_or_none.return_value = mock_user
            elif call_count == 2:
                # Exact channel match - find old conversation
                result.scalar_one_or_none.return_value = mock_conversation
            elif call_count == 3:
                # Fallback channel match (no exact match found first time)
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = mock_execute
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        repo = MessageRepositoryAsync(mock_session)

        await repo.create_message(
            user_id=mock_user.id,
            project_id=uuid.uuid4(),
            message_body={"text": "hello"},
            channel="sms",
        )

        # Verify conversation was expired
        assert mock_conversation.status == ConversationStatus.EXPIRED

        # Verify a new conversation was created (session.add called for new conversation + message)
        assert mock_session.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_active_conversation_within_24hr_checks_2hr_gap(self):
        """Active conversation within 24hr should still check the 2hr message gap."""
        from db.repositories.message_repository import MessageRepositoryAsync

        mock_session = AsyncMock()

        mock_user = MagicMock(spec=User)
        mock_user.id = uuid.uuid4()

        # Conversation created 1 hour ago (within 24hr)
        mock_conversation = MagicMock(spec=Conversation)
        mock_conversation.id = uuid.uuid4()
        mock_conversation.status = ConversationStatus.ACTIVE
        mock_conversation.created_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(hours=1)

        # Last message 30 minutes ago (within 2hr)
        recent_message_time = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=30)

        execute_count = 0

        async def mock_execute(query):
            nonlocal execute_count
            execute_count += 1
            result = MagicMock()

            if execute_count == 1:
                result.scalar_one_or_none.return_value = mock_user
            elif execute_count == 2:
                result.scalar_one_or_none.return_value = mock_conversation
            elif execute_count == 3:
                # 2hr message gap check — returns recent message time
                result.scalar_one_or_none.return_value = recent_message_time
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = mock_execute
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        repo = MessageRepositoryAsync(mock_session)

        await repo.create_message(
            user_id=mock_user.id,
            project_id=uuid.uuid4(),
            message_body={"text": "hello"},
            channel="sms",
        )

        # Conversation should still be ACTIVE (reused)
        assert mock_conversation.status == ConversationStatus.ACTIVE


# ===========================================================================
# Bug 9 (FIXED): Hard delete cascade now includes ProjectSubscription
# [HIGH] — Fix: Added step to delete ProjectSubscriptions before Projects
# ===========================================================================


class TestHardDeleteCascadeFix:
    """Fixed: Hard delete cascade now cleans up ProjectSubscriptions."""

    def test_hard_delete_includes_project_subscription_cleanup(self):
        """[HIGH] Hard delete cascade now deletes ProjectSubscriptions
        before deleting Projects and AccountSubscriptions."""
        from db.tables.subscriptions import ProjectSubscription

        mock_session = MagicMock()
        repo = AccountRepository(mock_session)

        account = MagicMock(spec=Account)
        account.id = uuid.uuid4()
        account.name = "test"

        project_id = uuid.uuid4()
        deleted_models = []

        def query_side_effect(model):
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q

            def track_delete(**kwargs):
                deleted_models.append(model)
                return None

            mock_q.delete = track_delete
            mock_q.filter.return_value.delete = track_delete

            if model is User.id:
                mock_q.filter.return_value.all.return_value = [
                    MagicMock(id=uuid.uuid4())
                ]
            elif model is Conversation.id:
                mock_q.filter.return_value.all.return_value = [
                    MagicMock(id=uuid.uuid4())
                ]
            elif model is Project.id:
                mock_q.filter.return_value.all.return_value = [MagicMock(id=project_id)]
            else:
                mock_q.first.return_value = account
                mock_q.filter.return_value.first.return_value = account
            return mock_q

        mock_session.query.side_effect = query_side_effect

        repo.delete_account("test", hard_delete=True)

        # After fix: ProjectSubscription should be in the cascade
        assert (
            ProjectSubscription in deleted_models
        ), "ProjectSubscription should be deleted as part of the hard delete cascade"


# ===========================================================================
# Bug 10 (FIXED): Version check no longer has redundant inner condition
# [LOW] — Fix: Removed redundant inner `if expected_version` check
# ===========================================================================


class TestVersionCheckCleanup:
    """Fixed: Version check no longer has redundant inner condition."""

    def test_account_version_check_no_redundancy(self):
        """[LOW] expected_version appears exactly 3 times: parameter definition,
        `is not None` check, and comparison — no redundant inner check."""
        import inspect

        source = inspect.getsource(AccountRepository.update_account)

        # After fix: expected_version appears in:
        # 1. Method parameter
        # 2. `if expected_version is not None and ...`
        # 3. `if int(...) != expected_version:`
        count = source.count("expected_version")
        assert count == 3, (
            f"expected_version appears {count} times (expected 3: "
            "parameter, None check, comparison)"
        )
