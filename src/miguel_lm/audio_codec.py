from __future__ import annotations

import audioop
import io
import wave


def wav_bytes_to_pcm16_mono(wav_bytes: bytes, target_sample_rate: int) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        source_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
        sample_width = 2
    if channels > 1:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
    if source_rate != target_sample_rate:
        frames, _state = audioop.ratecv(frames, sample_width, 1, source_rate, target_sample_rate, None)
    return frames


def pcm16_mono_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()
