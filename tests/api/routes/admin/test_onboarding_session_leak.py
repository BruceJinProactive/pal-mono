"""Tests for onboarding DB connection leak fix.

Verifies that self_onboard_voice_config uses `async with AsyncSessionLocal()`
instead of bare `AsyncSessionLocal()` without context manager.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Mock async session that tracks context manager usage."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _make_request(language: str = "English") -> MagicMock:
    """Create a mock SelfOnboardingRequest."""
    mock_request = MagicMock()
    mock_request.agent_language = language
    mock_request.agent_greeting_message = "Hello"
    mock_request.agent_voice_id = "voice-123"
    return mock_request


class TestOnboardingSessionLeak:
    """Verify self_onboard_voice_config uses async context manager."""

    @pytest.mark.asyncio
    async def test_no_bare_async_session_local(self) -> None:
        """The function must use `async with AsyncSessionLocal()`, not bare constructor."""
        import inspect

        from api.routes.admin._onboarding import self_onboard_voice_config

        source = inspect.getsource(self_onboard_voice_config)

        lines = source.split("\n")
        has_context_manager = any(
            "async with" in line and "AsyncSessionLocal" in line for line in lines
        )
        assert has_context_manager, (
            "self_onboard_voice_config must use "
            "`async with AsyncSessionLocal() as session:`"
        )

    @pytest.mark.asyncio
    async def test_session_context_manager_on_success(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """Verify __aenter__/__aexit__ are called when voice config creation succeeds."""
        mock_voice_config = MagicMock()
        mock_voice_config.id = uuid.uuid4()

        with (
            patch("api.routes.admin._onboarding.AsyncSessionLocal") as mock_factory,
            patch("api.routes.admin._onboarding.VoiceService") as mock_voice_svc_cls,
            patch(
                "api.routes.admin._onboarding._get_language_config",
                return_value={
                    "language": "English",
                    "first_message": "Hi",
                    "transfer_message": "Transferring",
                },
            ),
        ):
            mock_factory.return_value = mock_async_session
            mock_voice_svc = AsyncMock()
            mock_voice_svc.create_voice_config = AsyncMock(
                return_value=mock_voice_config
            )
            mock_voice_svc_cls.return_value = mock_voice_svc

            from api.routes.admin._onboarding import self_onboard_voice_config

            await self_onboard_voice_config(
                project_id=uuid.uuid4(),
                request=_make_request("English"),
                context=MagicMock(),
                session=MagicMock(),
            )

            mock_async_session.__aenter__.assert_awaited_once()
            mock_async_session.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multilingual_path_uses_context_manager(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """Multilingual path also uses context manager and creates all configs."""
        mock_voice_config = MagicMock()
        mock_voice_config.id = uuid.uuid4()

        with (
            patch("api.routes.admin._onboarding.AsyncSessionLocal") as mock_factory,
            patch("api.routes.admin._onboarding.VoiceService") as mock_voice_svc_cls,
            patch(
                "api.routes.admin._onboarding._get_language_config",
                return_value={
                    "language": "English",
                    "first_message": "Hi",
                    "transfer_message": "Transferring",
                },
            ),
        ):
            mock_factory.return_value = mock_async_session
            mock_voice_svc = AsyncMock()
            mock_voice_svc.create_voice_config = AsyncMock(
                return_value=mock_voice_config
            )
            mock_voice_svc_cls.return_value = mock_voice_svc

            from api.routes.admin._onboarding import self_onboard_voice_config

            await self_onboard_voice_config(
                project_id=uuid.uuid4(),
                request=_make_request("Multilingual"),
                context=MagicMock(),
                session=MagicMock(),
            )

            mock_async_session.__aenter__.assert_awaited_once()
            mock_async_session.__aexit__.assert_awaited_once()
            # Multilingual creates 4 configs: English, Spanish, Chinese, Triage
            assert mock_voice_svc.create_voice_config.await_count == 4

    @pytest.mark.asyncio
    async def test_error_path_rolls_back_and_closes_session(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """On error, session is rolled back and context manager still exits."""
        with (
            patch("api.routes.admin._onboarding.AsyncSessionLocal") as mock_factory,
            patch("api.routes.admin._onboarding.VoiceService") as mock_voice_svc_cls,
            patch(
                "api.routes.admin._onboarding._get_language_config",
                return_value={
                    "language": "English",
                    "first_message": "Hi",
                    "transfer_message": "Transferring",
                },
            ),
        ):
            mock_factory.return_value = mock_async_session
            mock_voice_svc = AsyncMock()
            mock_voice_svc.create_voice_config = AsyncMock(
                side_effect=RuntimeError("voice creation failed")
            )
            mock_voice_svc_cls.return_value = mock_voice_svc

            from api.routes.admin._onboarding import self_onboard_voice_config

            with pytest.raises(HTTPException) as exc_info:
                await self_onboard_voice_config(
                    project_id=uuid.uuid4(),
                    request=_make_request("English"),
                    context=MagicMock(),
                    session=MagicMock(),
                )

            assert exc_info.value.status_code == 400
            mock_async_session.rollback.assert_awaited_once()
            mock_async_session.__aenter__.assert_awaited_once()
            mock_async_session.__aexit__.assert_awaited_once()
