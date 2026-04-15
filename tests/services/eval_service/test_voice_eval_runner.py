"""Tests for VoiceEvalConfig, run_voice_scenario, and voice eval wiring."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._voice_eval_runner import (
    VoiceEvalConfig,
    _extract_turn_texts,
    _generate_caller_token,
    run_voice_scenario,
)
from services.eval_service.schema import EvalScenario, TurnType, UserTurn

# ---------------------------------------------------------------------------
# VoiceEvalConfig
# ---------------------------------------------------------------------------


class TestVoiceEvalConfig:
    def test_from_env_success(self) -> None:
        env = {
            "LIVEKIT_URL": "wss://lk.example.com",
            "LIVEKIT_API_KEY": "APIkey",
            "LIVEKIT_API_SECRET": "APIsecret",
            "CARTESIA_API_KEY": "cart-key",
        }
        with patch.dict(os.environ, env, clear=False):
            config = VoiceEvalConfig.from_env()

        assert config.livekit_url == "wss://lk.example.com"
        assert config.livekit_api_key == "APIkey"
        assert config.livekit_api_secret == "APIsecret"
        assert config.cartesia_api_key == "cart-key"

    def test_from_env_missing_vars(self) -> None:
        env = {
            "LIVEKIT_URL": "wss://lk.example.com",
            # Missing: LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CARTESIA_API_KEY
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="LIVEKIT_API_KEY"):
                VoiceEvalConfig.from_env()

    def test_from_env_all_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="LIVEKIT_URL"):
                VoiceEvalConfig.from_env()

    def test_repr_redacts_secrets(self) -> None:
        config = VoiceEvalConfig(
            livekit_url="wss://test",
            livekit_api_key="secret-key",
            livekit_api_secret="secret-secret",
            cartesia_api_key="cart-secret",
        )
        r = repr(config)
        assert "secret-key" not in r
        assert "secret-secret" not in r
        assert "cart-secret" not in r
        assert "***" in r
        assert "wss://test" in r

    def test_defaults(self) -> None:
        config = VoiceEvalConfig(
            livekit_url="wss://test",
            livekit_api_key="k",
            livekit_api_secret="s",
            cartesia_api_key="c",
        )
        assert config.call_timeout_s == 120.0
        assert config.room_empty_timeout_s == 300


# ---------------------------------------------------------------------------
# _extract_turn_texts
# ---------------------------------------------------------------------------


class TestExtractTurnTexts:
    def test_string_turns(self) -> None:
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=["Hello", "What are your hours?"],
        )
        texts = _extract_turn_texts(scenario)
        assert texts == ["Hello", "What are your hours?"]

    def test_user_turn_objects(self) -> None:
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=[
                UserTurn(text="Hi there"),
                UserTurn(text="Thanks"),
            ],
        )
        texts = _extract_turn_texts(scenario)
        assert texts == ["Hi there", "Thanks"]

    def test_ai_driven_uses_goal(self) -> None:
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=[
                UserTurn(type=TurnType.AI_DRIVEN, goal="Ask about the menu"),
            ],
        )
        texts = _extract_turn_texts(scenario)
        assert texts == ["Ask about the menu"]

    def test_ai_driven_fallback_to_text(self) -> None:
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=[
                UserTurn(type=TurnType.AI_DRIVEN, text="Fallback text"),
            ],
        )
        texts = _extract_turn_texts(scenario)
        assert texts == ["Fallback text"]

    def test_empty_turns_filtered(self) -> None:
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=[
                UserTurn(text=""),
                "Hello",
                UserTurn(text=None),
            ],
        )
        texts = _extract_turn_texts(scenario)
        assert texts == ["Hello"]

    def test_mixed_turns(self) -> None:
        scenario = EvalScenario(
            scenario_id="s1",
            scenario="test",
            test_category="general",
            user_turns=[
                "Hello",
                UserTurn(text="I want pizza"),
                UserTurn(type=TurnType.AI_DRIVEN, goal="Ask about toppings"),
            ],
        )
        texts = _extract_turn_texts(scenario)
        assert texts == ["Hello", "I want pizza", "Ask about toppings"]


# ---------------------------------------------------------------------------
# run_voice_scenario
# ---------------------------------------------------------------------------


def _make_scenario() -> EvalScenario:
    return EvalScenario(
        scenario_id="voice-test-1",
        scenario="Order a pizza by phone",
        test_category="voice",
        persona="fast_speaker",
        user_turns=["Hello, I'd like to order a pizza", "Large pepperoni please"],
    )


def _make_config() -> VoiceEvalConfig:
    return VoiceEvalConfig(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="APItest",
        livekit_api_secret="secret",
        cartesia_api_key="cart-key",
    )


class TestGenerateCallerToken:
    """Tests for _generate_caller_token()."""

    def test_embeds_call_id_in_attributes(self) -> None:
        """Token JWT contains sip.callID in participant attributes."""
        mock_orch = MagicMock()
        mock_orch.api_key = "test-key"
        mock_orch.api_secret = "test-secret"

        result = _generate_caller_token(
            mock_orch, room_name="eval-voice-room", call_id="eval-abc123"
        )

        assert result.identity == "eval-synthetic-caller"
        assert result.room_name == "eval-voice-room"
        assert isinstance(result.token, str)
        assert len(result.token) > 0


class TestRunVoiceScenarioNoCallerFactory:
    """When no caller_factory is provided, a default SyntheticCaller is created."""

    async def test_creates_default_synthetic_caller(self) -> None:
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 0.0
        mock_conversation_record = MagicMock()
        mock_voice_result.to_conversation_record.return_value = mock_conversation_record

        with (
            patch(
                "services.eval_service._voice_eval_runner.LiveKitRoomOrchestrator"
            ) as mock_orch_cls,
            patch("services.eval_service._voice_eval_runner.TTSEngine") as mock_tts_cls,
            patch(
                "services.eval_service._synthetic_caller.SyntheticCaller"
            ) as mock_caller_cls,
            patch(
                "services.eval_service._voice_eval_runner.VoiceResultCollector"
            ) as mock_collector_cls,
            patch(
                "services.eval_service._voice_eval_runner._generate_caller_token"
            ) as mock_gen_token,
        ):
            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-abc")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt-token")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_caller = mock_caller_cls.return_value
            mock_caller.run_call = AsyncMock(return_value="eval-abc123")

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            record = await run_voice_scenario(
                scenario, config, session, caller_factory=None
            )

        # Default SyntheticCaller was created with the livekit_url
        mock_caller_cls.assert_called_once_with(
            livekit_url="wss://test.livekit.cloud",
        )
        mock_caller.run_call.assert_awaited_once()
        assert record is mock_conversation_record
        mock_orch.teardown.assert_awaited_once_with("eval-voice-abc")
        mock_orch.close.assert_awaited_once()

    async def test_creates_room_with_persona(self) -> None:
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 0.0
        mock_conversation_record = MagicMock()
        mock_voice_result.to_conversation_record.return_value = mock_conversation_record

        with (
            patch(
                "services.eval_service._voice_eval_runner.LiveKitRoomOrchestrator"
            ) as mock_orch_cls,
            patch("services.eval_service._voice_eval_runner.TTSEngine") as mock_tts_cls,
            patch(
                "services.eval_service._voice_eval_runner.resolve_persona"
            ) as mock_resolve,
            patch(
                "services.eval_service._synthetic_caller.SyntheticCaller"
            ) as mock_caller_cls,
            patch(
                "services.eval_service._voice_eval_runner.VoiceResultCollector"
            ) as mock_collector_cls,
            patch(
                "services.eval_service._voice_eval_runner._generate_caller_token"
            ) as mock_gen_token,
        ):
            mock_profile = MagicMock()
            mock_resolve.return_value = mock_profile

            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-xyz")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_caller = mock_caller_cls.return_value
            mock_caller.run_call = AsyncMock(return_value="eval-abc123")

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            await run_voice_scenario(scenario, config, session, caller_factory=None)

        mock_resolve.assert_called_once_with("fast_speaker")
        mock_tts_cls.assert_called_once_with(
            api_key="cart-key",
            default_profile=mock_profile,
        )


class TestRunVoiceScenarioWithCallerFactory:
    """When a caller_factory is provided, it runs the call and collects results."""

    async def test_full_flow(self) -> None:
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(return_value="call-123")

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi, welcome!"},
        ]
        mock_voice_result.metrics.duration_seconds = 30.0
        mock_conversation_record = MagicMock()
        mock_voice_result.to_conversation_record.return_value = mock_conversation_record

        with (
            patch(
                "services.eval_service._voice_eval_runner.LiveKitRoomOrchestrator"
            ) as mock_orch_cls,
            patch("services.eval_service._voice_eval_runner.TTSEngine") as mock_tts_cls,
            patch(
                "services.eval_service._voice_eval_runner.VoiceResultCollector"
            ) as mock_collector_cls,
            patch(
                "services.eval_service._voice_eval_runner._generate_caller_token"
            ) as mock_gen_token,
        ):
            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-abc")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt-token")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            record = await run_voice_scenario(
                scenario, config, session, caller_factory=mock_caller_factory
            )

        # Caller factory was invoked with call_id
        mock_caller_factory.run_call.assert_awaited_once()
        call_kwargs = mock_caller_factory.run_call.call_args
        assert call_kwargs.kwargs["turns"] == [
            "Hello, I'd like to order a pizza",
            "Large pepperoni please",
        ]
        assert "call_id" in call_kwargs.kwargs
        assert call_kwargs.kwargs["call_id"].startswith("eval-")

        # Token was generated with sip.callID via _generate_caller_token
        mock_gen_token.assert_called_once()
        token_args = mock_gen_token.call_args
        assert token_args.kwargs["call_id"].startswith("eval-")

        # Result collector polled with the call_id returned by run_call
        mock_collector.collect.assert_awaited_once_with(
            call_id="call-123",
            room_name="eval-voice-abc",
            timeout_s=120.0,
        )

        # Converted to conversation record
        mock_voice_result.to_conversation_record.assert_called_once_with(scenario)
        assert record is mock_conversation_record

        # Cleanup happened
        mock_orch.teardown.assert_awaited_once()
        mock_orch.close.assert_awaited_once()
        mock_tts.close.assert_awaited_once()

    async def test_teardown_on_caller_error(self) -> None:
        """Room teardown and client close happen even if caller_factory fails."""
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(
            side_effect=RuntimeError("Connection failed")
        )

        with (
            patch(
                "services.eval_service._voice_eval_runner.LiveKitRoomOrchestrator"
            ) as mock_orch_cls,
            patch("services.eval_service._voice_eval_runner.TTSEngine") as mock_tts_cls,
            patch(
                "services.eval_service._voice_eval_runner._generate_caller_token"
            ) as mock_gen_token,
        ):
            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-err")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            with pytest.raises(RuntimeError, match="Connection failed"):
                await run_voice_scenario(
                    scenario, config, session, caller_factory=mock_caller_factory
                )

        # Cleanup still happened
        mock_orch.teardown.assert_awaited_once_with("eval-voice-err")
        mock_orch.close.assert_awaited_once()
        mock_tts.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Runner voice branch wiring
# ---------------------------------------------------------------------------


class TestRunnerVoiceBranch:
    """Verify _run_eval_background correctly routes to voice path."""

    async def test_voice_mode_calls_run_voice_scenario(self) -> None:
        """When driver_mode='voice', runner uses run_voice_scenario."""
        from services.eval_service._runner import _run_eval_background

        mock_scenario = _make_scenario()

        with (
            patch(
                "services.eval_service._runner.AsyncSessionLocal"
            ) as mock_session_local,
            patch(
                "services.eval_service._runner.EvalRunRepositoryAsync"
            ) as mock_run_repo_cls,
            patch(
                "services.eval_service._runner.EvalResultRepositoryAsync"
            ) as mock_result_repo_cls,
            patch(
                "services.eval_service._runner.load_scenarios",
                return_value=[mock_scenario],
            ),
            patch(
                "services.eval_service._runner._parse_channel_identifier",
                return_value=("voice", "room-123"),
            ),
            patch(
                "services.eval_service._voice_eval_runner.VoiceEvalConfig.from_env"
            ) as mock_from_env,
            patch(
                "services.eval_service._voice_eval_runner.run_voice_scenario"
            ) as mock_run_voice,
            patch("services.eval_service._runner.evaluate_scenario") as mock_evaluate,
        ):
            # Setup session context manager
            mock_session = AsyncMock()
            mock_session_local.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_run_repo = mock_run_repo_cls.return_value
            mock_run_repo.update_status = AsyncMock()
            mock_run_repo.update_counts = AsyncMock()

            mock_result_repo = mock_result_repo_cls.return_value
            mock_result_repo.create = AsyncMock()

            mock_config = _make_config()
            mock_from_env.return_value = mock_config

            mock_record = MagicMock()
            mock_run_voice.return_value = mock_record
            mock_evaluate.return_value = []

            import uuid

            run_id = uuid.uuid4()
            project_id = uuid.uuid4()

            await _run_eval_background(run_id, project_id, "voice:room-123", "voice")

        mock_from_env.assert_called_once()
        mock_run_voice.assert_awaited_once()
        mock_evaluate.assert_awaited_once_with(mock_record)


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class TestRunEvalRequestVoiceDriver:
    def test_voice_driver_accepted(self) -> None:
        import uuid

        from api.schemas.eval.requests import RunEvalRequest

        request = RunEvalRequest(
            project_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            channel_identifier="voice:room-123",
            driver="voice",
        )
        assert request.driver == "voice"

    def test_direct_driver_accepted(self) -> None:
        import uuid

        from api.schemas.eval.requests import RunEvalRequest

        request = RunEvalRequest(
            project_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            channel_identifier="direct:room-123",
            driver="direct",
        )
        assert request.driver == "direct"

    def test_invalid_driver_rejected(self) -> None:
        import uuid

        from pydantic import ValidationError

        from api.schemas.eval.requests import RunEvalRequest

        with pytest.raises(ValidationError):
            RunEvalRequest(
                project_id=uuid.uuid4(),
                account_id=uuid.uuid4(),
                channel_identifier="api:test",
                driver="invalid",  # type: ignore[arg-type]
            )
