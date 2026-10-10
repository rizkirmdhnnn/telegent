#!/usr/bin/env python3
"""
PoC Gemini Live API - Streaming Suara Dua Arah (Fase 1)

Mendukung:
1. Mode Interaktif Mikrofon & Speaker (sounddevice)
2. Mode Simulasi Berkas Audio (File-based testing)
3. Deteksi Interupsi / Barge-in
4. Bahasa Indonesia (System Instruction)
"""

import argparse
import asyncio
import os
import sys
import wave
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Format Audio Standar Gemini Live API
INPUT_SAMPLE_RATE = 16000  # 16 kHz
INPUT_CHANNELS = 1         # Mono
INPUT_CHUNK_MS = 20        # 20 ms per chunk
INPUT_CHUNK_BYTES = int(INPUT_SAMPLE_RATE * (INPUT_CHUNK_MS / 1000.0) * 2)  # 640 bytes (16-bit)

OUTPUT_SAMPLE_RATE = 24000  # 24 kHz
OUTPUT_CHANNELS = 1         # Mono

DEFAULT_MODEL = "gemini-2.5-flash-native-audio-latest"

SYSTEM_INSTRUCTION = (
    "Anda adalah asisten suara AI yang ramah, ringkas, dan berbicara dalam bahasa Indonesia yang santun "
    "dan natural seperti sedang berbicara di telepon. Jawab secara padat (1-2 kalimat) karena ini adalah percakapan telepon langsung."
)


class GeminiAudioAgent:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY tidak ditemukan. Mohon setel environment variable GEMINI_API_KEY.")

        self.model = model
        self.client = genai.Client(api_key=self.api_key)
        self.playback_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.is_interrupted = False
        self.is_running = True

    def flush_playback(self):
        """Mengosongkan queue audio ketika interupsi/barge-in terdeteksi."""
        dropped_chunks = 0
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
                dropped_chunks += 1
            except asyncio.QueueEmpty:
                break
        if dropped_chunks > 0:
            print(f"\n[Barge-In] Interupsi terdeteksi! Mengosongkan {dropped_chunks} chunk audio dari buffer.")

    async def receive_loop(self, session, on_audio_chunk=None):
        """Mendengarkan respons streaming dari Gemini Live API."""
        try:
            async for response in session.receive():
                if not self.is_running:
                    break

                server_content = response.server_content
                if server_content is not None:
                    # Penanganan interupsi (User Barge-in)
                    if server_content.interrupted:
                        self.flush_playback()
                        continue

                    # Ekstraksi potongan audio
                    model_turn = server_content.model_turn
                    if model_turn and model_turn.parts:
                        for part in model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                audio_bytes = part.inline_data.data
                                await self.playback_queue.put(audio_bytes)
                                if on_audio_chunk:
                                    await on_audio_chunk(audio_bytes)

                    # Penanda akhir giliran AI
                    if server_content.turn_complete:
                        print(" [AI selesai bicara]", end="", flush=True)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"\n[Error receive_loop] {type(e).__name__}: {e}", file=sys.stderr)

    async def run_live_mic(self):
        """Menjalankan sesi live interaktif menggunakan mikrofon dan speaker lokal."""
        try:
            import sounddevice as sd
        except ImportError:
            print("Error: Library 'sounddevice' belum terpasang. Jalankan: pip install sounddevice", file=sys.stderr)
            return

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=SYSTEM_INSTRUCTION)]
            ),
        )

        audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def mic_callback(indata, _frames, _time_info, status):
            if status:
                print(f"[Mic status] {status}", file=sys.stderr)
            # Konversi array numpy float/int16 ke raw 16-bit PCM bytes
            raw_pcm = indata.tobytes()
            loop.call_soon_threadsafe(audio_in_queue.put_nowait, raw_pcm)

        def speaker_callback(outdata, frames, _time_info, status):
            if status:
                print(f"[Speaker status] {status}", file=sys.stderr)
            needed_bytes = frames * 2  # 16-bit mono = 2 bytes per sample
            collected = bytearray()
            while len(collected) < needed_bytes:
                try:
                    chunk = self.playback_queue.get_nowait()
                    collected.extend(chunk)
                except asyncio.QueueEmpty:
                    break

            if len(collected) < needed_bytes:
                # Isi sisanya dengan hening jika buffer kosong
                collected.extend(b"\x00" * (needed_bytes - len(collected)))

            outdata[:] = bytes(collected[:needed_bytes])

        print(f"Membuka koneksi WebSocket ke Gemini Live API (Model: {self.model})...")
        async with self.client.aio.live.connect(model=self.model, config=config) as session:
            print("Koneksi Gemini Live API terhubung!")
            print("Silakan mulai berbicara ke mikrofon Anda dalam bahasa Indonesia. Tekan Ctrl+C untuk berhenti.")

            # Buka audio stream I/O via sounddevice
            chunk_frames = int(INPUT_SAMPLE_RATE * (INPUT_CHUNK_MS / 1000.0))
            mic_stream = sd.RawInputStream(
                samplerate=INPUT_SAMPLE_RATE,
                channels=INPUT_CHANNELS,
                dtype="int16",
                blocksize=chunk_frames,
                callback=mic_callback,
            )
            speaker_stream = sd.RawOutputStream(
                samplerate=OUTPUT_SAMPLE_RATE,
                channels=OUTPUT_CHANNELS,
                dtype="int16",
                blocksize=int(OUTPUT_SAMPLE_RATE * 0.02),  # 20 ms blocks
                callback=speaker_callback,
            )

            async def send_mic_loop():
                try:
                    while self.is_running:
                        chunk = await audio_in_queue.get()
                        await session.send_realtime_input(
                            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                        )
                except asyncio.CancelledError:
                    pass

            with mic_stream, speaker_stream:
                receiver_task = asyncio.create_task(self.receive_loop(session))
                sender_task = asyncio.create_task(send_mic_loop())

                try:
                    await asyncio.gather(receiver_task, sender_task)
                except asyncio.CancelledError:
                    pass
                finally:
                    receiver_task.cancel()
                    sender_task.cancel()

    async def run_file_simulation(self, input_wav_path: str, output_wav_path: str):
        """Menjalankan simulasi berbasis berkas untuk lingkungan pengujian otomatis."""
        input_path = Path(input_wav_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Berkas input {input_wav_path} tidak ditemukan.")

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=SYSTEM_INSTRUCTION)]
            ),
        )

        received_audio = bytearray()

        async def collect_audio(chunk: bytes):
            received_audio.extend(chunk)

        print(f"Membuka koneksi Gemini Live API untuk berkas: {input_wav_path}...")
        async with self.client.aio.live.connect(model=self.model, config=config) as session:
            print("Terhubung. Membaca berkas input...")
            receiver_task = asyncio.create_task(self.receive_loop(session, on_audio_chunk=collect_audio))

            with wave.open(str(input_path), "rb") as wf:
                channels = wf.getnchannels()
                rate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                print(f"Input Info: Channels={channels}, Rate={rate}Hz, Width={sampwidth * 8}bit")

                chunk_frames = int(rate * (INPUT_CHUNK_MS / 1000.0))
                while True:
                    frames = wf.readframes(chunk_frames)
                    if not frames:
                        break
                    await session.send_realtime_input(
                        audio=types.Blob(data=frames, mime_type=f"audio/pcm;rate={rate}")
                    )
                    await asyncio.sleep(INPUT_CHUNK_MS / 1000.0)

            # Tunggu respons selesai
            print("\nMenunggu respons model selesai...")
            await asyncio.sleep(4.0)
            self.is_running = False
            receiver_task.cancel()

            # Simpan respons ke WAV
            with wave.open(output_wav_path, "wb") as out_wf:
                out_wf.setnchannels(OUTPUT_CHANNELS)
                out_wf.setsampwidth(2)  # 16-bit
                out_wf.setframerate(OUTPUT_SAMPLE_RATE)
                out_wf.writeframes(bytes(received_audio))

            print(f"Respons audio tersimpan di: {output_wav_path} ({len(received_audio)} bytes)")


def main():
    parser = argparse.ArgumentParser(description="PoC Gemini Live API Streaming")
    parser.add_argument("--mode", choices=["mic", "file"], default="mic", help="Mode eksekusi: mic atau file")
    parser.add_argument("--input", type=str, help="Path ke berkas audio input WAV (untuk mode file)")
    parser.add_argument("--output", type=str, default="gemini_response.wav", help="Path berkas audio output")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Model ID Gemini Live")
    args = parser.parse_args()

    agent = GeminiAudioAgent(model=args.model)

    if args.mode == "mic":
        try:
            asyncio.run(agent.run_live_mic())
        except KeyboardInterrupt:
            print("\nSesi dihentikan oleh pengguna.")
    else:
        if not args.input:
            print("Error: Argumen --input diperlukan untuk mode file.", file=sys.stderr)
            sys.exit(1)
        asyncio.run(agent.run_file_simulation(args.input, args.output))


if __name__ == "__main__":
    main()
