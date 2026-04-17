"""Tests for the LiveKit voice init endpoint (api/routes/internal/_voice.py)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.internal._voice import _resolve_greeting, init_voice_call
from api.schemas.internal.voice_init import VoiceInitRequest, VoiceInitResponse
from db.tables.types import SpeechRate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides) -> VoiceInitRequest:
    defaults = {
        "caller_number": "+15551234567",
        "dialed_number": "+15559876543",
        "call_id": "call-abc-123",
    }
    defaults.update(overrides)
    return VoiceInitRequest(**defaults)


def _make_project(**overrides) -> MagicMock:
    project = MagicMock()
    project.id = overrides.get("id", uuid.uuid4())
    project.timezone = overrides.get("timezone", "America/New_York")
    project.account = MagicMock()
    project.account.id = uuid.uuid4()
    return project


def _make_voice_config(**overrides) -> MagicMock:
    vc = MagicMock()
    vc.language = overrides.get("language", "english")
    vc.voice_id = overrides.get("voice_id", "voice-abc")
    vc.speech_rate = overrides.get("speech_rate", SpeechRate.normal)
    vc.first_message = overrides.get("first_message", "Hello, how can I help?")
    vc.background_sound = overrides.get("background_sound", "office")
    vc.pronunciation_dict_id = overrides.get("pronunciation_dict_id", None)
    return vc


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _patch_deps(
    project: MagicMock | None,
    user: MagicMock,
    *,
    block_calls: bool = False,
    user_exists: bool = True,
) -> tuple:
    """Return a tuple of patch context managers for all ``init_voice_call`` deps."""
    return (
        patch(
            "api.routes.internal._voice.project_service.get_project_async",
            new_callable=AsyncMock,
            return_value=project,
        ),
        patch(
            "api.routes.internal._voice.user_service.get_user_async",
            new_callable=AsyncMock,
            return_value=(user if user_exists else None, None),
        ),
        patch(
            "api.routes.internal._voice.user_service.create_user_async",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("api.routes.internal._voice.db.MessageRepositoryAsync"),
        patch("api.routes.internal._voice.VoiceConfigRepository"),
    )


async def _run(
    request: VoiceInitRequest,
    project: MagicMock,
    user: MagicMock,
    voice_configs: list[MagicMock],
    *,
    block_calls: bool = False,
    user_exists: bool = True,
) -> VoiceInitResponse:
    """Run ``init_voice_call`` with all deps patched and return the response."""
    session = AsyncMock()
    p = _patch_deps(
        project,
        user,
        block_calls=block_calls,
        user_exists=user_exists,
    )
    with p[0], p[1], p[2], p[3] as msg_cls, p[4] as vc_cls:
        msg_cls.return_value = AsyncMock()
        vc_repo = AsyncMock()
        vc_repo.list_by_project_id.return_value = voice_configs
        vc_cls.return_value = vc_repo
        return await init_voice_call(request, session)


async def _run_expecting_error(
    request: VoiceInitRequest,
    project: MagicMock | None,
    user: MagicMock,
    voice_configs: list[MagicMock],
    *,
    block_calls: bool = False,
) -> HTTPException:
    """Run ``init_voice_call`` and return the raised HTTPException."""
    session = AsyncMock()
    p = _patch_deps(project, user, block_calls=block_calls)
    with p[0], p[1], p[2], p[3] as msg_cls, p[4] as vc_cls:
        msg_cls.return_value = AsyncMock()
        vc_repo = AsyncMock()
        vc_repo.list_by_project_id.return_value = voice_configs
        vc_cls.return_value = vc_repo
        with pytest.raises(HTTPException) as exc_info:
            await init_voice_call(request, session)
        return exc_info.value


# ---------------------------------------------------------------------------
# _resolve_greeting unit tests
# ---------------------------------------------------------------------------


class TestResolveGreeting:
    """Tests for the _resolve_greeting helper."""

    def test_no_placeholder_returns_unchanged(self) -> None:
        assert _resolve_greeting("Hello!", "America/New_York", "english") == "Hello!"

    def test_greet_placeholder_replaced_english(self) -> None:
        result = _resolve_greeting("{{greet}} Welcome!", "America/New_York", "english")
        assert "{{greet}}" not in result
        assert "Welcome!" in result
        assert any(
            g in result for g in ("Good morning!", "Good afternoon!", "Good evening!")
        )

    def test_greet_placeholder_replaced_spanish(self) -> None:
        result = _resolve_greeting(
            "{{greet}} Bienvenido!", "America/New_York", "spanish"
        )
        assert "{{greet}}" not in result
        assert "Bienvenido!" in result

    def test_unsupported_language_strips_placeholder(self) -> None:
        result = _resolve_greeting("{{greet}} Hello!", "America/New_York", "klingon")
        assert "{{greet}}" not in result
        assert "Hello!" in result

    def test_invalid_timezone_strips_placeholder(self) -> None:
        result = _resolve_greeting("{{greet}} Hello!", "Invalid/Timezone", "english")
        assert "{{greet}}" not in result
        assert "Hello!" in result


# ---------------------------------------------------------------------------
# init_voice_call tests — error branches
# ---------------------------------------------------------------------------


class TestInitVoiceCallProjectNotFound:
    """Project lookup returns None -> 404."""

    @pytest.mark.asyncio
    async def test_returns_404(self) -> None:
        exc = await _run_expecting_error(
            _make_request(),
            project=None,
            user=_make_user(),
            voice_configs=[],
        )
        assert exc.status_code == 404
        assert "Project not found" in exc.detail


class TestInitVoiceCallNoVoiceConfigs:
    """No voice configs for project -> 404."""

    @pytest.mark.asyncio
    async def test_returns_404_empty_list(self) -> None:
        exc = await _run_expecting_error(
            _make_request(),
            project=_make_project(),
            user=_make_user(),
            voice_configs=[],
        )
        assert exc.status_code == 404
        assert "No voice configuration found" in exc.detail


# ---------------------------------------------------------------------------
# init_voice_call tests — success paths
# ---------------------------------------------------------------------------


class TestInitVoiceCallSuccess:
    """Happy-path: returns VoiceInitResponse with correct fields."""

    @pytest.mark.asyncio
    async def test_response_fields(self) -> None:
        vc = _make_voice_config(
            first_message="Hello, how can I help?",
            voice_id="voice-xyz",
            speech_rate=SpeechRate.faster,
            background_sound="cafe",
        )
        result = await _run(
            _make_request(),
            _make_project(timezone="America/New_York"),
            _make_user(),
            [vc],
        )
        assert isinstance(result, VoiceInitResponse)
        assert result.voice_id == "voice-xyz"
        assert result.speech_rate == 1.25
        assert result.languages == ["english"]
        assert result.background_sound == "cafe"
        assert result.first_message == "Hello, how can I help?"

    @pytest.mark.asyncio
    async def test_greet_placeholder_resolved(self) -> None:
        vc = _make_voice_config(
            first_message="{{greet}} Welcome to the restaurant!",
            language="english",
        )
        result = await _run(
            _make_request(),
            _make_project(timezone="America/New_York"),
            _make_user(),
            [vc],
        )
        assert "{{greet}}" not in result.first_message
        assert "Welcome to the restaurant!" in result.first_message

    @pytest.mark.asyncio
    async def test_caller_info_populated(self) -> None:
        project = _make_project(
            timezone="US/Pacific",
        )
        vc = _make_voice_config()
        result = await _run(
            _make_request(
                caller_number="+15551111111",
                dialed_number="+15552222222",
                call_id="call-999",
            ),
            project,
            _make_user(),
            [vc],
        )
        assert result.caller_info["sender_identifier"] == "+15551111111"
        assert result.caller_info["recipient_identifier"] == "+15552222222"
        assert result.caller_info["call_id"] == "call-999"
        assert result.caller_info["timezone"] == "US/Pacific"

    @pytest.mark.asyncio
    async def test_null_first_message_uses_default(self) -> None:
        vc = _make_voice_config(first_message=None)
        result = await _run(_make_request(), _make_project(), _make_user(), [vc])
        assert result.first_message == "Hi, how can I help you today?"

    @pytest.mark.asyncio
    async def test_null_background_sound(self) -> None:
        vc = _make_voice_config(background_sound=None)
        result = await _run(_make_request(), _make_project(), _make_user(), [vc])
        assert result.background_sound is None

    @pytest.mark.asyncio
    async def test_multiple_configs_prefers_english(self) -> None:
        """Multiple voice configs should prefer English for voice_id but aggregate all languages."""
        spanish = _make_voice_config(language="spanish", voice_id="spanish-voice")
        english = _make_voice_config(language="english", voice_id="english-voice")
        result = await _run(
            _make_request(), _make_project(), _make_user(), [spanish, english]
        )
        assert result.voice_id == "english-voice"
        assert result.languages == ["spanish", "english"]

    @pytest.mark.asyncio
    async def test_multiple_configs_no_english_uses_first(self) -> None:
        """When multiple configs with no English, use first."""
        spanish = _make_voice_config(language="spanish", voice_id="spanish-voice")
        chinese = _make_voice_config(language="chinese", voice_id="chinese-voice")
        result = await _run(
            _make_request(), _make_project(), _make_user(), [spanish, chinese]
        )
        assert result.voice_id == "spanish-voice"
        assert result.languages == ["spanish", "chinese"]

    @pytest.mark.asyncio
    async def test_languages_deduplicated(self) -> None:
        """Duplicate languages should be removed."""
        vc1 = _make_voice_config(language="english", voice_id="voice1")
        vc2 = _make_voice_config(language="spanish", voice_id="voice2")
        vc3 = _make_voice_config(language="english", voice_id="voice3")
        result = await _run(
            _make_request(), _make_project(), _make_user(), [vc1, vc2, vc3]
        )
        assert result.languages == ["english", "spanish"]

    @pytest.mark.asyncio
    async def test_user_creation_path(self) -> None:
        """When get_user_async returns None, create_user_async is called."""
        session = AsyncMock()
        project = _make_project()
        user = _make_user()
        vc = _make_voice_config()
        p = _patch_deps(project, user, user_exists=False)
        with (
            p[0],
            p[1] as mock_get_user,
            p[2] as mock_create_user,
            p[3] as msg_cls,
            p[4] as vc_cls,
        ):
            msg_cls.return_value = AsyncMock()
            vc_repo = AsyncMock()
            vc_repo.list_by_project_id.return_value = [vc]
            vc_cls.return_value = vc_repo

            result = await init_voice_call(_make_request(), session)

        mock_get_user.assert_awaited_once()
        mock_create_user.assert_awaited_once()
        assert isinstance(result, VoiceInitResponse)


# ---------------------------------------------------------------------------
# Speech rate mapping tests
# ---------------------------------------------------------------------------


class TestSpeechRateMapping:
    """Verify all SpeechRate enum values map to correct floats."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "rate,expected",
        [
            (SpeechRate.slowest, 0.6),
            (SpeechRate.slower, 0.8),
            (SpeechRate.normal, 1.0),
            (SpeechRate.faster, 1.25),
            (SpeechRate.fastest, 1.5),
        ],
    )
    async def test_speech_rate(self, rate: SpeechRate, expected: float) -> None:
        vc = _make_voice_config(speech_rate=rate)
        result = await _run(_make_request(), _make_project(), _make_user(), [vc])
        assert result.speech_rate == expected
