#!/usr/bin/env python3
"""
Membuat berkas WAV uji coba 16 kHz 16-bit mono untuk simulasi pengujian Gemini Live API.
"""
import math
import struct
import wave
from pathlib import Path

def generate_sine_wave(output_path: str, duration_sec: float = 3.0, freq_hz: float = 440.0, sample_rate: int = 16000):
    num_samples = int(duration_sec * sample_rate)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        for i in range(num_samples):
            # Sinusoidal tone
            value = int(16000 * math.sin(2 * math.pi * freq_hz * (i / sample_rate)))
            data = struct.pack("<h", value)
            wf.writeframes(data)

    print(f"Berkas audio uji berhasil dibuat: {output_path} ({duration_sec}s, {sample_rate}Hz)")

if __name__ == "__main__":
    generate_sine_wave("tests/test_input_16k.wav")
