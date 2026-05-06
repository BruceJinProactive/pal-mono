"""Tests for VoiceEvalConfig, run_voice_scenario, and voice eval wiring."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._voice_eval_runner import (
    VoiceEvalConfig,
    _extract_turn_texts,
    _generate_caller_token,
    _start_room_egress,
    _stop_and_collect_egress,
    run_voice_scenario,
)
from services.eval_service.schema import EvalScenario, TurnType, UserTurn

# ---------------------------------------------------------------------------
# VoiceEvalConfig
# ---------------------------------------------------------------------------


class TestVoiceEvalConfig:
    def test_from_env_success(self) -> None:
        secrets = {
            "LIVEKIT_URL": "wss://lk.example.com",
            "LIVEKIT_API_KEY": "APIkey",
            "LIVEKIT_API_SECRET": "APIsecret",
            "CARTESIA_VOICE_EVAL_API_KEY": "cart-key",
        }
        with patch(
            "services.eval_service._voice_eval_runner.get_server_secret_with_fallback",
            side_effect=lambda k: secrets[k],
        ):
            config = VoiceEvalConfig.from_env()

        assert config.livekit_url == "wss://lk.example.com"
        assert config.livekit_api_key == "APIkey"
        assert config.livekit_api_secret == "APIsecret"
        assert config.cartesia_api_key == "cart-key"

    def test_from_env_missing_vars(self) -> None:
        secrets = {"LIVEKIT_URL": "wss://lk.example.com"}

        def _lookup(key: str) -> str:
            if key in secrets:
                return secrets[key]
            raise ValueError(f"not found: {key}")

        with patch(
            "services.eval_service._voice_eval_runner.get_server_secret_with_fallback",
            side_effect=_lookup,
        ):
            with pytest.raises(ValueError, match="LIVEKIT_API_KEY"):
                VoiceEvalConfig.from_env()

    def test_from_env_all_missing(self) -> None:
        with patch(
            "services.eval_service._voice_eval_runner.get_server_secret_with_fallback",
            side_effect=ValueError("not found"),
        ):
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
        assert config.recording_s3_bucket == ""
        assert config.recording_s3_region == "us-east-1"

    def test_from_env_with_recording_config(self) -> None:
        secrets = {
            "LIVEKIT_URL": "wss://lk.example.com",
            "LIVEKIT_API_KEY": "APIkey",
            "LIVEKIT_API_SECRET": "APIsecret",
            "CARTESIA_VOICE_EVAL_API_KEY": "cart-key",
        }
        env = {
            "VOICE_EVAL_RECORDING_BUCKET": "my-eval-bucket",
            "VOICE_EVAL_RECORDING_REGION": "us-west-2",
        }
        with (
            patch(
                "services.eval_service._voice_eval_runner.get_server_secret_with_fallback",
                side_effect=lambda k: secrets[k],
            ),
            patch.dict(os.environ, env, clear=False),
        ):
            config = VoiceEvalConfig.from_env()

        assert config.recording_s3_bucket == "my-eval-bucket"
        assert config.recording_s3_region == "us-west-2"


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

    def test_embeds_phone_numbers_when_dialed_number_provided(self) -> None:
        """Token includes sip.phoneNumber and sip.trunkPhoneNumber when dialed_number is set."""
        import jwt

        mock_orch = MagicMock()
        mock_orch.api_key = "test-key"
        mock_orch.api_secret = "test-secret"

        result = _generate_caller_token(
            mock_orch,
            room_name="eval-voice-room",
            call_id="eval-abc123",
            dialed_number="+18001234567",
        )

        decoded = jwt.decode(result.token, options={"verify_signature": False})
        attrs = decoded.get("attributes", {})
        assert attrs["sip.callID"] == "eval-abc123"
        assert attrs["sip.phoneNumber"] == "+10000000000"
        assert attrs["sip.trunkPhoneNumber"] == "+18001234567"

    def test_no_phone_numbers_when_dialed_number_empty(self) -> None:
        """Token omits phone number attributes when dialed_number is empty."""
        import jwt

        mock_orch = MagicMock()
        mock_orch.api_key = "test-key"
        mock_orch.api_secret = "test-secret"

        result = _generate_caller_token(
            mock_orch,
            room_name="eval-voice-room",
            call_id="eval-abc123",
            dialed_number="",
        )

        decoded = jwt.decode(result.token, options={"verify_signature": False})
        attrs = decoded.get("attributes", {})
        assert attrs["sip.callID"] == "eval-abc123"
        assert "sip.phoneNumber" not in attrs
        assert "sip.trunkPhoneNumber" not in attrs

    def test_strips_whitespace_from_dialed_number(self) -> None:
        """Whitespace-only dialed_number is treated as empty."""
        import jwt

        mock_orch = MagicMock()
        mock_orch.api_key = "test-key"
        mock_orch.api_secret = "test-secret"

        result = _generate_caller_token(
            mock_orch,
            room_name="eval-voice-room",
            call_id="eval-abc123",
            dialed_number="  ",
        )

        decoded = jwt.decode(result.token, options={"verify_signature": False})
        attrs = decoded.get("attributes", {})
        assert "sip.trunkPhoneNumber" not in attrs


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
            audio_recording_s3_uri=None,
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
# Voice overrides
# ---------------------------------------------------------------------------


class TestVoiceOverridesInRunVoiceScenario:
    """Verify run_voice_scenario applies voice_overrides for speed and noise."""

    async def test_speed_override_applied(self) -> None:
        """When voice_overrides has 'speed', the VoiceProfile is reconstructed."""
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(return_value="call-speed")

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 10.0
        mock_voice_result.to_conversation_record.return_value = MagicMock()

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
            patch(
                "services.eval_service._voice_eval_runner.resolve_persona"
            ) as mock_resolve,
            patch(
                "services.eval_service._voice_eval_runner.VoiceProfile"
            ) as mock_vp_cls,
            patch(
                "pal_agents.evals.voice.personas.get_persona_config"
            ) as mock_persona_cfg,
        ):
            mock_profile = MagicMock()
            mock_profile.voice_id = "voice-1"
            mock_profile.model = "sonic"
            mock_profile.language = "en"
            mock_profile.speed = 1.0
            mock_profile.sample_rate = 24000
            mock_resolve.return_value = mock_profile

            # When VoiceProfile(...) is called for the speed override,
            # return a mock with the new speed
            mock_new_profile = MagicMock()
            mock_new_profile.speed = 1.8
            mock_new_profile.sample_rate = 24000
            mock_vp_cls.return_value = mock_new_profile

            mock_persona_cfg.return_value = MagicMock(
                background_noise=False, noise_level_db=-20.0
            )

            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-speed")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            await run_voice_scenario(
                scenario,
                config,
                session,
                caller_factory=mock_caller_factory,
                voice_overrides={"speed": 1.8},
            )

        # VoiceProfile was reconstructed with the override speed
        mock_vp_cls.assert_called_once_with(
            voice_id="voice-1",
            model="sonic",
            language="en",
            speed=1.8,
            sample_rate=24000,
        )
        # The caller_factory received the new profile
        call_kwargs = mock_caller_factory.run_call.call_args.kwargs
        assert call_kwargs["voice_profile"] is mock_new_profile

    async def test_noise_overrides_applied(self) -> None:
        """When voice_overrides has noise fields, noise_config reflects them."""
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(return_value="call-noise")

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 10.0
        mock_voice_result.to_conversation_record.return_value = MagicMock()

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
            patch(
                "services.eval_service._voice_eval_runner.resolve_persona"
            ) as mock_resolve,
            patch(
                "pal_agents.evals.voice.personas.get_persona_config"
            ) as mock_persona_cfg,
        ):
            mock_profile = MagicMock()
            mock_profile.voice_id = "voice-1"
            mock_profile.model = "sonic"
            mock_profile.language = "en"
            mock_profile.speed = 1.0
            mock_profile.sample_rate = 24000
            mock_resolve.return_value = mock_profile

            mock_persona_cfg.return_value = MagicMock(
                background_noise=False, noise_level_db=-20.0
            )

            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-noise")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            await run_voice_scenario(
                scenario,
                config,
                session,
                caller_factory=mock_caller_factory,
                voice_overrides={
                    "background_noise": True,
                    "noise_level_db": -10.0,
                    "noise_type": "car",
                },
            )

        # The caller_factory should receive a NoiseConfig with overrides
        call_kwargs = mock_caller_factory.run_call.call_args.kwargs
        noise_cfg = call_kwargs["noise_config"]
        assert noise_cfg.enabled is True
        assert noise_cfg.noise_level_db == -10.0
        assert noise_cfg.noise_type.value == "car"


# ---------------------------------------------------------------------------
# voice_params metadata on ConversationRecord
# ---------------------------------------------------------------------------


class TestVoiceParamsMetadata:
    """Verify run_voice_scenario attaches voice_params to the returned record."""

    async def test_voice_params_populated(self) -> None:
        """Returned ConversationRecord.voice_params has resolved settings."""
        session = AsyncMock()
        config = _make_config()
        scenario = _make_scenario()

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(return_value="call-meta")

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 10.0
        # to_conversation_record returns a real-ish record
        from services.eval_service._evaluators import ConversationRecord

        real_record = ConversationRecord(scenario=scenario, is_voice=True)
        mock_voice_result.to_conversation_record.return_value = real_record

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
            patch(
                "services.eval_service._voice_eval_runner.resolve_persona"
            ) as mock_resolve,
            patch(
                "pal_agents.evals.voice.personas.get_persona_config"
            ) as mock_persona_cfg,
        ):
            mock_profile = MagicMock()
            mock_profile.voice_id = "voice-1"
            mock_profile.speed = 1.5
            mock_profile.sample_rate = 24000
            mock_resolve.return_value = mock_profile

            mock_persona_cfg.return_value = MagicMock(
                background_noise=True, noise_level_db=-15.0
            )

            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-meta")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()

            mock_gen_token.return_value = MagicMock(token="jwt")

            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            record = await run_voice_scenario(
                scenario,
                config,
                session,
                caller_factory=mock_caller_factory,
            )

        assert record.voice_params is not None
        assert record.voice_params["persona"] == "fast_speaker"
        assert record.voice_params["speed"] == 1.5
        assert record.voice_params["background_noise"] is True
        assert record.voice_params["noise_level_db"] == -15.0
        assert record.voice_params["noise_type"] == "street"


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


# ---------------------------------------------------------------------------
# _start_room_egress / _stop_and_collect_egress
# ---------------------------------------------------------------------------

RUNNER_MODULE = "services.eval_service._voice_eval_runner"


class TestStartRoomEgress:
    """Tests for _start_room_egress helper."""

    async def test_returns_none_when_no_bucket(self) -> None:
        config = _make_config()
        assert config.recording_s3_bucket == ""

        result = await _start_room_egress(
            MagicMock(), "eval-voice-room", "eval-abc", config
        )
        assert result is None

    async def test_starts_egress_and_returns_id(self) -> None:
        config = VoiceEvalConfig(
            livekit_url="wss://test",
            livekit_api_key="k",
            livekit_api_secret="s",
            cartesia_api_key="c",
            recording_s3_bucket="eval-bucket",
        )

        mock_egress_info = MagicMock()
        mock_egress_info.egress_id = "eg-123"

        lk_api = MagicMock()
        lk_api.egress.start_room_composite_egress = AsyncMock(
            return_value=mock_egress_info
        )

        result = await _start_room_egress(lk_api, "eval-voice-room", "eval-abc", config)

        assert result == "eg-123"
        lk_api.egress.start_room_composite_egress.assert_awaited_once()
        request = lk_api.egress.start_room_composite_egress.call_args[0][0]
        assert request.room_name == "eval-voice-room"
        assert request.audio_only is True

    async def test_returns_none_on_exception(self) -> None:
        config = VoiceEvalConfig(
            livekit_url="wss://test",
            livekit_api_key="k",
            livekit_api_secret="s",
            cartesia_api_key="c",
            recording_s3_bucket="eval-bucket",
        )

        lk_api = MagicMock()
        lk_api.egress.start_room_composite_egress = AsyncMock(
            side_effect=RuntimeError("egress unavailable")
        )

        result = await _start_room_egress(lk_api, "eval-voice-room", "eval-abc", config)
        assert result is None


class TestStopAndCollectEgress:
    """Tests for _stop_and_collect_egress helper."""

    async def test_returns_s3_uri_on_success_full_uri(self) -> None:
        """When location is a full S3 URI, return it as-is (no double prefix)."""
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock()

        mock_file_result = MagicMock()
        mock_file_result.location = "s3://eval-bucket/eval-recordings/room/call.ogg"

        mock_egress_info = MagicMock()
        mock_egress_info.status = 3  # EGRESS_COMPLETE
        mock_egress_info.file_results = [mock_file_result]

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")

        assert result == "s3://eval-bucket/eval-recordings/room/call.ogg"
        lk_api.egress.stop_egress.assert_awaited_once()

    async def test_returns_s3_uri_on_success_bare_path(self) -> None:
        """When location is a bare path, prefix with s3://bucket/."""
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock()

        mock_file_result = MagicMock()
        mock_file_result.location = "eval-recordings/room/call.ogg"

        mock_egress_info = MagicMock()
        mock_egress_info.status = 3  # EGRESS_COMPLETE
        mock_egress_info.file_results = [mock_file_result]

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")

        assert result == "s3://eval-bucket/eval-recordings/room/call.ogg"
        lk_api.egress.stop_egress.assert_awaited_once()

    async def test_still_polls_after_stop_failure(self) -> None:
        """If stop_egress fails, we still poll — egress may already be complete."""
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock(side_effect=RuntimeError("stop failed"))

        mock_file_result = MagicMock()
        mock_file_result.location = "s3://eval-bucket/eval-recordings/room/call.ogg"

        mock_egress_info = MagicMock()
        mock_egress_info.status = 3  # EGRESS_COMPLETE
        mock_egress_info.file_results = [mock_file_result]

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")

        assert result == "s3://eval-bucket/eval-recordings/room/call.ogg"
        lk_api.egress.list_egress.assert_awaited_once()

    async def test_returns_none_on_egress_failed(self) -> None:
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock()

        mock_egress_info = MagicMock()
        mock_egress_info.status = 4  # EGRESS_FAILED
        mock_egress_info.file_results = []

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")
        assert result is None

    async def test_returns_none_on_egress_failed_with_file_results(self) -> None:
        """Failed egress should not return a URI even if file_results exist."""
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock()

        mock_file_result = MagicMock()
        mock_file_result.location = "s3://eval-bucket/partial-recording.ogg"

        mock_egress_info = MagicMock()
        mock_egress_info.status = 4  # EGRESS_FAILED
        mock_egress_info.file_results = [mock_file_result]

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")
        assert result is None

    async def test_returns_none_on_limit_reached(self) -> None:
        """EGRESS_LIMIT_REACHED (6) is treated as terminal failure."""
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock()

        mock_egress_info = MagicMock()
        mock_egress_info.status = 6  # EGRESS_LIMIT_REACHED
        mock_egress_info.file_results = []

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")
        assert result is None

    async def test_returns_none_when_no_file_location(self) -> None:
        lk_api = MagicMock()
        lk_api.egress.stop_egress = AsyncMock()

        mock_file_result = MagicMock()
        mock_file_result.location = ""

        mock_egress_info = MagicMock()
        mock_egress_info.status = 3  # EGRESS_COMPLETE
        mock_egress_info.file_results = [mock_file_result]

        mock_response = MagicMock()
        mock_response.items = [mock_egress_info]
        lk_api.egress.list_egress = AsyncMock(return_value=mock_response)

        result = await _stop_and_collect_egress(lk_api, "eg-123", "eval-bucket")
        assert result is None


class TestRunVoiceScenarioWithEgress:
    """Tests for egress integration in run_voice_scenario."""

    async def test_egress_started_when_bucket_configured(self) -> None:
        session = AsyncMock()
        config = VoiceEvalConfig(
            livekit_url="wss://test.livekit.cloud",
            livekit_api_key="APItest",
            livekit_api_secret="secret",
            cartesia_api_key="cart-key",
            recording_s3_bucket="eval-bucket",
        )
        scenario = _make_scenario()

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 0.0
        mock_voice_result.audio_recording_s3_uri = (
            "s3://eval-bucket/eval-recordings/room/call.ogg"
        )
        mock_conversation_record = MagicMock()
        mock_voice_result.to_conversation_record.return_value = mock_conversation_record

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(return_value="call-123")

        with (
            patch(f"{RUNNER_MODULE}.LiveKitRoomOrchestrator") as mock_orch_cls,
            patch(f"{RUNNER_MODULE}.TTSEngine") as mock_tts_cls,
            patch(f"{RUNNER_MODULE}.VoiceResultCollector") as mock_collector_cls,
            patch(f"{RUNNER_MODULE}._generate_caller_token") as mock_gen_token,
            patch(f"{RUNNER_MODULE}._start_room_egress") as mock_start_egress,
            patch(f"{RUNNER_MODULE}._stop_and_collect_egress") as mock_stop_egress,
            patch("livekit.api.LiveKitAPI") as mock_lk_api_cls,
        ):
            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-abc")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()
            mock_gen_token.return_value = MagicMock(token="jwt")
            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_lk_api = mock_lk_api_cls.return_value
            mock_lk_api.aclose = AsyncMock()

            mock_start_egress.return_value = "eg-456"
            mock_stop_egress.return_value = (
                "s3://eval-bucket/eval-recordings/room/call.ogg"
            )

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            await run_voice_scenario(
                scenario, config, session, caller_factory=mock_caller_factory
            )

        mock_start_egress.assert_awaited_once()
        mock_stop_egress.assert_awaited_once_with(mock_lk_api, "eg-456", "eval-bucket")
        mock_collector.collect.assert_awaited_once()
        collect_kwargs = mock_collector.collect.call_args.kwargs
        assert (
            collect_kwargs["audio_recording_s3_uri"]
            == "s3://eval-bucket/eval-recordings/room/call.ogg"
        )
        mock_lk_api.aclose.assert_awaited_once()

    async def test_egress_stopped_in_finally_on_call_failure(self) -> None:
        """Egress is stopped even if run_call() raises, via the finally block."""
        session = AsyncMock()
        config = VoiceEvalConfig(
            livekit_url="wss://test.livekit.cloud",
            livekit_api_key="APItest",
            livekit_api_secret="secret",
            cartesia_api_key="cart-key",
            recording_s3_bucket="eval-bucket",
        )
        scenario = _make_scenario()

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(
            side_effect=RuntimeError("Call exploded")
        )

        with (
            patch(f"{RUNNER_MODULE}.LiveKitRoomOrchestrator") as mock_orch_cls,
            patch(f"{RUNNER_MODULE}.TTSEngine") as mock_tts_cls,
            patch(f"{RUNNER_MODULE}._generate_caller_token") as mock_gen_token,
            patch(f"{RUNNER_MODULE}._start_room_egress") as mock_start_egress,
            patch(f"{RUNNER_MODULE}._stop_and_collect_egress") as mock_stop_egress,
            patch("livekit.api.LiveKitAPI") as mock_lk_api_cls,
        ):
            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-fail")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()
            mock_gen_token.return_value = MagicMock(token="jwt")
            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_lk_api = mock_lk_api_cls.return_value
            mock_lk_api.aclose = AsyncMock()

            mock_start_egress.return_value = "eg-789"
            mock_stop_egress.return_value = None

            with pytest.raises(RuntimeError, match="Call exploded"):
                await run_voice_scenario(
                    scenario, config, session, caller_factory=mock_caller_factory
                )

        # Egress was started and then stopped in the finally block
        mock_start_egress.assert_awaited_once()
        mock_stop_egress.assert_awaited_once_with(mock_lk_api, "eg-789", "eval-bucket")
        # LiveKit API client was closed
        mock_lk_api.aclose.assert_awaited_once()
        # Room teardown still happened
        mock_orch.teardown.assert_awaited_once_with("eval-voice-fail")

    async def test_no_egress_when_bucket_empty(self) -> None:
        session = AsyncMock()
        config = _make_config()  # no recording_s3_bucket
        scenario = _make_scenario()

        mock_voice_result = MagicMock()
        mock_voice_result.transcript = []
        mock_voice_result.metrics.duration_seconds = 0.0
        mock_conversation_record = MagicMock()
        mock_voice_result.to_conversation_record.return_value = mock_conversation_record

        mock_caller_factory = AsyncMock()
        mock_caller_factory.run_call = AsyncMock(return_value="call-123")

        with (
            patch(f"{RUNNER_MODULE}.LiveKitRoomOrchestrator") as mock_orch_cls,
            patch(f"{RUNNER_MODULE}.TTSEngine") as mock_tts_cls,
            patch(f"{RUNNER_MODULE}.VoiceResultCollector") as mock_collector_cls,
            patch(f"{RUNNER_MODULE}._generate_caller_token") as mock_gen_token,
            patch(f"{RUNNER_MODULE}._start_room_egress") as mock_start_egress,
        ):
            mock_orch = mock_orch_cls.return_value
            mock_orch.create_room = AsyncMock(
                return_value=MagicMock(room_name="eval-voice-abc")
            )
            mock_orch.teardown = AsyncMock()
            mock_orch.close = AsyncMock()
            mock_gen_token.return_value = MagicMock(token="jwt")
            mock_tts = mock_tts_cls.return_value
            mock_tts.close = AsyncMock()

            mock_collector = mock_collector_cls.return_value
            mock_collector.collect = AsyncMock(return_value=mock_voice_result)

            await run_voice_scenario(
                scenario, config, session, caller_factory=mock_caller_factory
            )

        mock_start_egress.assert_not_called()
        collect_kwargs = mock_collector.collect.call_args.kwargs
        assert collect_kwargs["audio_recording_s3_uri"] is None
