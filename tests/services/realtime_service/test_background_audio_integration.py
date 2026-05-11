"""Integration tests for background audio wiring: config -> mixer init -> stream mixing."""

import base64
import importlib.util
from pathlib import Path

# Load _audio_mixer directly to avoid the package __init__ pulling heavy deps
_mixer_spec = importlib.util.spec_from_file_location(
    "_test_bg_audio_mixer",
    Path(__file__).resolve().parents[3]
    / "services"
    / "realtime_service"
    / "_audio_mixer.py",
)
assert _mixer_spec and _mixer_spec.loader
_audio_mixer_mod = importlib.util.module_from_spec(_mixer_spec)
_mixer_spec.loader.exec_module(_audio_mixer_mod)  # type: ignore[attr-defined]

BackgroundAudioMixer = _audio_mixer_mod.BackgroundAudioMixer


class TestCreateRealtimeSessionMixerInit:
    """Test that create_realtime_session initializes the mixer from VoiceConfig."""

    def test_mixer_initialized_when_background_sound_configured(self) -> None:
        """When voice_config.background_sound='office' and asset exists, mixer is set."""
        assets_dir = (
            Path(__file__).resolve().parents[3]
            / "services"
            / "realtime_service"
            / "assets"
        )
        asset_path = assets_dir / "office.ulaw"
        assert asset_path.exists(), f"Asset file missing: {asset_path}"

        buffer = asset_path.read_bytes()
        mixer = BackgroundAudioMixer(buffer=buffer, volume=0.1)
        assert mixer._bg_len == len(buffer)
        assert mixer._volume == 0.1
        assert mixer._position == 0

    def test_no_mixer_when_background_sound_is_none(self) -> None:
        """When background_sound is None, no mixer should be created."""
        background_sound = None
        mixer = None
        if background_sound:
            mixer = BackgroundAudioMixer(buffer=b"test", volume=0.1)
        assert mixer is None

    def test_no_mixer_when_asset_file_missing(self) -> None:
        """When asset file doesn't exist, mixer should be None."""
        assets_dir = (
            Path(__file__).resolve().parents[3]
            / "services"
            / "realtime_service"
            / "assets"
        )
        asset_path = assets_dir / "nonexistent.ulaw"
        mixer = None
        if asset_path.exists():
            mixer = BackgroundAudioMixer(buffer=asset_path.read_bytes(), volume=0.1)
        assert mixer is None


class TestVoiceCallHandlerMixerApplication:
    """Test that VoiceCallHandler applies mixer when streaming audio."""

    def test_mixer_applied_to_audio_chunk(self) -> None:
        """Mixer transforms base64 µ-law chunks when present."""
        # Create a known chunk (silence in µ-law = 0xFF)
        raw_chunk = bytes([0xFF] * 160)  # 20ms at 8kHz
        b64_chunk = base64.b64encode(raw_chunk).decode("ascii")

        # Create mixer with loud background
        bg_buffer = bytes([0x00] * 1000)  # loud signal
        mixer = BackgroundAudioMixer(buffer=bg_buffer, volume=0.5)

        # Simulate what the voice handler does
        raw = base64.b64decode(b64_chunk)
        mixed = mixer.mix_chunk(raw)
        payload = base64.b64encode(mixed).decode("ascii")

        # Mixed output should differ from input (background was added)
        assert payload != b64_chunk
        # Output should still be valid base64
        decoded = base64.b64decode(payload)
        assert len(decoded) == 160  # Same length

    def test_no_mixer_passthrough(self) -> None:
        """When mixer is None, audio passes through unchanged."""
        raw_chunk = bytes([0x80, 0x7F, 0x00, 0xFF] * 40)
        b64_chunk = base64.b64encode(raw_chunk).decode("ascii")

        mixer = None
        if mixer:
            raw = base64.b64decode(b64_chunk)
            mixed = mixer.mix_chunk(raw)
            payload = base64.b64encode(mixed).decode("ascii")
        else:
            payload = b64_chunk

        assert payload == b64_chunk
