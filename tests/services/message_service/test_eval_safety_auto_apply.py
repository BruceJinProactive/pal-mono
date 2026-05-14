"""Tests for eval-safety auto-apply in message_service.

Verifies that ``_apply_test_safety_if_needed`` hardens a ``Spec`` in
place iff the persisted Conversation is flagged ``is_test=True``. This
is the single choke point that makes every caller path
(``InProcessDriver``, ``HttpVoiceDriver``, real-voice LiveKit, direct
HTTP) safe by construction when scenarios set ``metadata.testing=True``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_spec() -> MagicMock:
    """Build a Spec-shaped mock that ``apply_eval_safety`` can mutate."""
    spec = MagicMock()
    spec.toast.enabled = True
    spec.toast.submit_orders = True
    spec.adora.enabled = True
    spec.adora.force_payment_link = False
    return spec


class TestApplyTestSafetyIfNeeded:
    @pytest.mark.asyncio
    async def test_hardens_spec_when_conversation_is_test(
        self, mock_spec: MagicMock
    ) -> None:
        from services.message_service._implementation import (
            _apply_test_safety_if_needed,
        )

        conversation = MagicMock()
        conversation.is_test = True

        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(return_value=conversation)

        session = MagicMock()

        with patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=repo,
        ):
            await _apply_test_safety_if_needed(session, uuid.uuid4(), mock_spec)

        assert mock_spec.toast.submit_orders is False
        assert mock_spec.adora.force_payment_link is True

    @pytest.mark.asyncio
    async def test_leaves_spec_unchanged_for_production_conversation(
        self, mock_spec: MagicMock
    ) -> None:
        from services.message_service._implementation import (
            _apply_test_safety_if_needed,
        )

        conversation = MagicMock()
        conversation.is_test = False

        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(return_value=conversation)

        session = MagicMock()

        with patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=repo,
        ):
            await _apply_test_safety_if_needed(session, uuid.uuid4(), mock_spec)

        # Safety NOT applied — production Specs pass through untouched.
        assert mock_spec.toast.submit_orders is True
        assert mock_spec.adora.force_payment_link is False

    @pytest.mark.asyncio
    async def test_missing_conversation_does_not_raise(
        self, mock_spec: MagicMock
    ) -> None:
        """If the repo raises ValueError (not found), the helper swallows it.

        Safety must never turn into a crash that masks other problems.
        """
        from services.message_service._implementation import (
            _apply_test_safety_if_needed,
        )

        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(
            side_effect=ValueError("no such conversation")
        )

        session = MagicMock()

        with patch(
            "services.message_service._implementation.db.ConversationRepositoryAsync",
            return_value=repo,
        ):
            # No exception.
            await _apply_test_safety_if_needed(session, uuid.uuid4(), mock_spec)

        # Spec untouched; no conversation means no is_test signal.
        assert mock_spec.toast.submit_orders is True
        assert mock_spec.adora.force_payment_link is False

    @pytest.mark.asyncio
    async def test_unexpected_error_is_logged_and_swallowed(
        self, mock_spec: MagicMock
    ) -> None:
        from services.message_service._implementation import (
            _apply_test_safety_if_needed,
        )

        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(side_effect=RuntimeError("db blew up"))

        session = MagicMock()

        with (
            patch(
                "services.message_service._implementation.db.ConversationRepositoryAsync",
                return_value=repo,
            ),
            patch("services.message_service._implementation.logger") as mock_logger,
        ):
            await _apply_test_safety_if_needed(session, uuid.uuid4(), mock_spec)

        # Logged exception, spec unchanged.
        mock_logger.exception.assert_called_once()
        assert mock_spec.toast.submit_orders is True


class TestApplyEvalSafetyReExport:
    def test_utils_canonical_and_service_shim_are_the_same_function(self) -> None:
        """Ensure the service-layer shim re-exports the canonical utils helper.

        The shim exists for backward compatibility with existing
        ``InProcessDriver`` and test imports. Moving the canonical
        implementation to ``utils.eval_safety`` closed the circular
        ``message_service → eval_service`` dependency.
        """
        from services.eval_service._safety import apply_eval_safety as shim_apply
        from utils.eval_safety import apply_eval_safety as canonical_apply

        assert shim_apply is canonical_apply
