import io
import json
import struct
import urllib.request
import wave

import pytest

from miguel_lm.audio_codec import pcm16_mono_to_wav_bytes, wav_bytes_to_pcm16_mono
from miguel_lm.config import AppConfig
from miguel_lm.providers.factory import build_tts_provider
from miguel_lm.providers.local_http_tts_provider import LocalHttpTTSProvider


def _wav_bytes(samples, sample_rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()


def test_factory_builds_local_http_tts_provider_by_default(monkeypatch):
    monkeypatch.delenv("LOCAL_TTS_ENDPOINT", raising=False)
    config = AppConfig.load("config/server.yaml")

    provider = build_tts_provider(config)

    assert isinstance(provider, LocalHttpTTSProvider)
    assert provider.endpoint == "http://127.0.0.1:7861/synthesize"
    assert provider.sample_rate == 24000


def test_pcm_to_wav_round_trip():
    pcm = b"\x00\x00\xe8\x03\x18\xfc"

    wav_payload = pcm16_mono_to_wav_bytes(pcm, 24000)

    assert wav_payload.startswith(b"RIFF")
    assert wav_bytes_to_pcm16_mono(wav_payload, 24000) == pcm


@pytest.mark.asyncio
async def test_local_http_tts_provider_posts_text_and_decodes_wav(monkeypatch):
    monkeypatch.delenv("LOCAL_TTS_ENDPOINT", raising=False)
    captured = {}
    wav_payload = _wav_bytes([0, 1000, -1000, 0])

    class FakeHeaders:
        def get(self, name, default=None):
            return "audio/wav" if name == "Content-Type" else default

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return wav_payload

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = LocalHttpTTSProvider(
        endpoint_env="LOCAL_TTS_ENDPOINT",
        default_endpoint="http://tts.local/synthesize",
        sample_rate=24000,
        timeout_seconds=12,
        ref_audio="assets/input/audio/f5_reference.wav",
        ref_text="reference words",
    )

    clip = await provider.synthesize("hello")

    assert clip.pcm == wav_bytes_to_pcm16_mono(wav_payload, 24000)
    assert clip.provider == "local_http_tts"
    assert captured["url"] == "http://tts.local/synthesize"
    assert captured["headers"]["Accept"] == "audio/wav"
    assert captured["payload"] == {
        "text": "hello",
        "ref_audio": "assets/input/audio/f5_reference.wav",
        "ref_text": "reference words",
    }
    assert captured["timeout"] == 12
