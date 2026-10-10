"""
Modul Resampling Audio Real-Time untuk Telegent.

Menangani konversi antara:
1. Telegram VoIP (48 kHz mono PCM s16le) -> Gemini Live Input (16 kHz mono PCM s16le) [Downsampling 3:1]
2. Gemini Live Output (24 kHz mono PCM s16le) -> Telegram VoIP (48 kHz mono PCM s16le) [Upsampling 1:2]
"""

import numpy as np


def pcm48k_to_pcm16k(pcm_data: bytes) -> bytes:
    """
    Konversi audio PCM 16-bit mono 48 kHz ke 16 kHz.
    Rasio: 1:3 downsampling dengan filter perata anti-aliasing tanpa edge-artifact.
    """
    if not pcm_data:
        return b""

    samples = np.frombuffer(pcm_data, dtype=np.int16)
    if len(samples) < 3:
        return b""

    # Truncate ke kelipatan 3
    n = (len(samples) // 3) * 3
    s = samples[:n].astype(np.int32)
    # Rata-rata 3 sampel adjacent (Low-Pass Filter anti-aliasing instan)
    downsampled = ((s[0::3] + s[1::3] + s[2::3]) // 3).astype(np.int16)
    return downsampled.tobytes()


def pcm24k_to_pcm48k(pcm_data: bytes) -> bytes:
    """
    Konversi audio PCM 16-bit mono 24 kHz ke 48 kHz.
    Rasio: 2:1 upsampling dengan interpolasi linier kontinu untuk mencegah distorsi klik/buzz.
    """
    if not pcm_data:
        return b""

    samples = np.frombuffer(pcm_data, dtype=np.int16)
    n = len(samples)
    if n == 0:
        return b""
    if n == 1:
        return np.repeat(samples, 2).tobytes()

    s = samples.astype(np.float32)
    mid = (s[:-1] + s[1:]) * 0.5

    out = np.empty(n * 2, dtype=np.int16)
    out[0::2] = s.astype(np.int16)
    out[1:-1:2] = np.clip(mid, -32768, 32767).astype(np.int16)
    out[-1] = s[-1]
    return out.tobytes()
