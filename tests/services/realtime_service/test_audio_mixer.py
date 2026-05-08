"""Tests for BackgroundAudioMixer µ-law audio mixing."""

import importlib.util
from pathlib import Path

# Load _audio_mixer directly to avoid the package __init__ pulling heavy deps
_spec = importlib.util.spec_from_file_location(
    "_test_audio_mixer",
    Path(__file__).resolve().parents[3]
    / "services"
    / "realtime_service"
    / "_audio_mixer.py",
)
assert _spec and _spec.loader
_audio_mixer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_audio_mixer)  # type: ignore[attr-defined]

BackgroundAudioMixer = _audio_mixer.BackgroundAudioMixer
_ULAW_DECODE = _audio_mixer._ULAW_DECODE


class TestBackgroundAudioMixer:
    """Tests for the BackgroundAudioMixer class."""

    def test_zero_volume_returns_original_chunk(self) -> None:
        buffer = bytes([0x7F] * 100)
        mixer = BackgroundAudioMixer(buffer=buffer, volume=0.0)
        chunk = bytes(range(256)) * 2
        result = mixer.mix_chunk(chunk)
        assert result == chunk

    def test_empty_buffer_returns_original_chunk(self) -> None:
        mixer = BackgroundAudioMixer(buffer=b"", volume=0.5)
        chunk = bytes([0x80, 0x7F, 0x00, 0xFF])
        result = mixer.mix_chunk(chunk)
        assert result == chunk

    def test_looping_wraps_position(self) -> None:
        buffer = bytes([0x7F, 0x80, 0xFF])  # 3 bytes
        mixer = BackgroundAudioMixer(buffer=buffer, volume=0.1)
        chunk = bytes([0x7F] * 7)  # 7 samples = wraps around buffer twice plus one
        mixer.mix_chunk(chunk)
        assert mixer._position == 1  # 7 % 3 = 1

    def test_position_advances_across_multiple_calls(self) -> None:
        buffer = bytes([0x7F] * 10)
        mixer = BackgroundAudioMixer(buffer=buffer, volume=0.1)
        mixer.mix_chunk(bytes([0x7F] * 3))
        assert mixer._position == 3
        mixer.mix_chunk(bytes([0x7F] * 4))
        assert mixer._position == 7
        mixer.mix_chunk(bytes([0x7F] * 5))
        assert mixer._position == 2  # 12 % 10 = 2

    def test_output_clamped_to_int16_range(self) -> None:
        # 0x00 decodes to max positive PCM (~+32124), 0x80 decodes to max negative (~-32124)
        # Use extreme volume to force overflow beyond int16 range
        loud_positive = bytes([0x00])
        buffer = bytes([0x00] * 10)
        mixer = BackgroundAudioMixer(buffer=buffer, volume=10.0)
        result = mixer.mix_chunk(loud_positive)
        # Clamped to +32767 → encodes to µ-law 0x00 (max positive saturated)
        assert result[0] == 0x00

        loud_negative = bytes([0x80])
        neg_buffer = bytes([0x80] * 10)
        mixer2 = BackgroundAudioMixer(buffer=neg_buffer, volume=10.0)
        result2 = mixer2.mix_chunk(loud_negative)
        # Clamped to -32768 → encodes to µ-law 0x80 (max negative saturated)
        assert result2[0] == 0x80

    def test_mixing_produces_different_output(self) -> None:
        # Silence in µ-law is 0xFF (or 0x7F depending on convention)
        # Use a non-silent background to verify mixing actually changes output
        silence = bytes([0xFF] * 10)  # near-silence foreground
        loud_bg = bytes([0x00] * 10)  # loud background
        mixer = BackgroundAudioMixer(buffer=loud_bg, volume=0.5)
        result = mixer.mix_chunk(silence)
        # With loud background at 50% volume, output should differ from input
        assert result != silence
