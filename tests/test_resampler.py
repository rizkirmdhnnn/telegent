#!/usr/bin/env python3
"""
Unit test untuk audio_resampler.
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from src.audio_resampler import pcm48k_to_pcm16k, pcm24k_to_pcm48k


class TestAudioResampler(unittest.TestCase):
    def test_downsampling_48k_to_16k(self):
        # 4800 samples pada 48 kHz (100 ms) = 9600 bytes
        samples_48k = (np.sin(np.linspace(0, 100, 4800)) * 10000).astype(np.int16)
        bytes_48k = samples_48k.tobytes()
        self.assertEqual(len(bytes_48k), 9600)

        bytes_16k = pcm48k_to_pcm16k(bytes_48k)
        samples_16k = np.frombuffer(bytes_16k, dtype=np.int16)
        # Rasio 3:1 -> harus 1600 samples (3200 bytes)
        self.assertEqual(len(samples_16k), 1600)
        self.assertEqual(len(bytes_16k), 3200)

    def test_upsampling_24k_to_48k(self):
        # 2400 samples pada 24 kHz (100 ms) = 4800 bytes
        samples_24k = (np.sin(np.linspace(0, 100, 2400)) * 10000).astype(np.int16)
        bytes_24k = samples_24k.tobytes()
        self.assertEqual(len(bytes_24k), 4800)

        bytes_48k = pcm24k_to_pcm48k(bytes_24k)
        samples_48k = np.frombuffer(bytes_48k, dtype=np.int16)
        # Rasio 1:2 -> harus 4800 samples (9600 bytes)
        self.assertEqual(len(samples_48k), 4800)
        self.assertEqual(len(bytes_48k), 9600)

    def test_empty_buffer(self):
        self.assertEqual(pcm48k_to_pcm16k(b""), b"")
        self.assertEqual(pcm24k_to_pcm48k(b""), b"")


if __name__ == "__main__":
    unittest.main()
