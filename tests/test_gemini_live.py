#!/usr/bin/env python3
"""
Pengujian langsung Gemini Live API:
Mengirim salam suara / teks dalam bahasa Indonesia dan memverifikasi penerimaan audio respons.
"""
import asyncio
import wave
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

async def test_live_audio():
    client = genai.Client()
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=types.Content(
            parts=[types.Part.from_text(text="Jawab dalam 1 kalimat bahasa Indonesia: Halo, ini pengujian sistem suara.")]
        )
    )

    output_path = Path("tests/gemini_live_test_output.wav")
    collected_audio = bytearray()

    print("Menghubungkan ke Gemini Live API (gemini-2.5-flash-native-audio-latest)...")
    async with client.aio.live.connect(model="gemini-2.5-flash-native-audio-latest", config=config) as session:
        print("Terhubung! Mengirim inisiasi percakapan...")
        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Halo! Apakah suara Anda aktif?")]
                )
            ],
            turn_complete=True
        )

        async for response in session.receive():
            sc = response.server_content
            if sc:
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            collected_audio.extend(part.inline_data.data)
                if sc.turn_complete:
                    print(f"Giliran selesai! Total audio diterima: {len(collected_audio)} bytes")
                    break

    # Simpan ke berkas WAV 24 kHz 16-bit mono
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(bytes(collected_audio))

    print(f"Berkas audio hasil pengujian tersimpan di: {output_path}")
    assert len(collected_audio) > 0, "Audio response kosong!"
    print("Tes Gemini Live API BERHASIL 100%!")

if __name__ == "__main__":
    asyncio.run(test_live_audio())
