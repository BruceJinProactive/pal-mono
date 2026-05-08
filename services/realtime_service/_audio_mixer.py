"""µ-law background audio mixer for Twilio realtime voice streams.

Mixes a looping background audio clip into outgoing µ-law chunks with minimal
overhead. Uses pre-computed lookup tables for both decode and encode to avoid
per-sample math in the hot path.
"""

# Pre-computed µ-law decode table: byte → signed 16-bit PCM sample
_ULAW_DECODE: tuple[int, ...] = tuple(
    (
        (-(((~b & 0x0F) << 1) + 33) << (((~b >> 4) & 0x07) + 2)) + 132
        if ~b & 0x80
        else ((((~b & 0x0F) << 1) + 33) << (((~b >> 4) & 0x07) + 2)) - 132
    )
    for b in range(256)
)

# Pre-computed µ-law encode table: signed 16-bit PCM sample → µ-law byte
# Covers full int16 range (-32768 to 32767) mapped to 0..65535 index
_ULAW_ENCODE: bytes = b""


def _build_encode_table() -> bytes:
    """Build a 65536-byte encode lookup table at module load."""
    table = bytearray(65536)
    for i in range(65536):
        sample = i - 32768  # Convert index to signed int16

        if sample < 0:
            sign = 0x80
            sample = -sample
        else:
            sign = 0

        sample = min(sample, 32635)
        sample += 132

        exponent = 7
        mask = 0x4000
        while exponent > 0 and not (sample & mask):
            exponent -= 1
            mask >>= 1

        mantissa = (sample >> (exponent + 3)) & 0x0F
        table[i] = ~(sign | (exponent << 4) | mantissa) & 0xFF

    return bytes(table)


_ULAW_ENCODE = _build_encode_table()


class BackgroundAudioMixer:
    """Mixes a looping µ-law background buffer into outgoing µ-law audio chunks.

    Pre-decodes the background buffer to PCM at init time so the per-frame
    hot path only does table lookups and integer addition.
    """

    def __init__(self, buffer: bytes, volume: float = 0.1) -> None:
        self._volume = volume
        self._position = 0

        # Pre-decode background µ-law to scaled PCM samples (done once)
        self._bg_pcm: tuple[int, ...] = tuple(
            int(_ULAW_DECODE[b] * volume) for b in buffer
        )
        self._bg_len = len(self._bg_pcm)

    def mix_chunk(self, chunk: bytes) -> bytes:
        """Mix background audio into a µ-law chunk. Returns new µ-law bytes."""
        if not self._bg_pcm or self._volume == 0.0:
            return chunk

        bg_pcm = self._bg_pcm
        bg_len = self._bg_len
        pos = self._position
        encode = _ULAW_ENCODE
        decode = _ULAW_DECODE

        result = bytearray(len(chunk))
        for i, b in enumerate(chunk):
            mixed = decode[b] + bg_pcm[pos]
            # Clamp to int16 and encode via lookup (index = sample + 32768)
            if mixed > 32767:
                mixed = 32767
            elif mixed < -32768:
                mixed = -32768
            result[i] = encode[mixed + 32768]
            pos += 1
            if pos >= bg_len:
                pos = 0

        self._position = pos
        return bytes(result)
