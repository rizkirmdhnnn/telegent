"""Wrapper media `ntgcalls` untuk satu panggilan."""

from __future__ import annotations

import ntgcalls


class NtgAudioSink:
    """Implementasi `AudioSink` yang mengirim frame ke mikrofon panggilan via ntgcalls."""

    def __init__(self, ntg: ntgcalls.NTgCalls, user_id: int) -> None:
        self._ntg = ntg
        self._user_id = user_id
        self._frame_data = ntgcalls.FrameData(0, ntgcalls.VideoRotation.VIDEO_ROTATION_0, 0, 0)

    async def send_frame(self, frame: bytes) -> None:
        await self._ntg.send_external_frame(
            self._user_id,
            ntgcalls.StreamDevice.MICROPHONE,
            frame,
            self._frame_data,
        )


def external_audio_media(
    sample_rate: int = 48000, *, keep_open: bool = True
) -> ntgcalls.MediaDescription:
    """MediaDescription EXTERNAL pada slot `microphone`.

    Quirk ntgcalls 3.x: sink PLAYBACK juga harus diarahkan ke slot `microphone`
    agar frame audio masuk diteruskan ke callback `on_frames` (bukan ke speaker OS).
    """
    audio = ntgcalls.AudioDescription(
        media_source=ntgcalls.MediaSource.EXTERNAL,
        sample_rate=sample_rate,
        channel_count=1,
        input="",
        keep_open=keep_open,
    )
    return ntgcalls.MediaDescription(audio, None, None, None)
