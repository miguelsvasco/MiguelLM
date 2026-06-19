import base64
import io
import json
import struct
import urllib.request
import wave

import pytest

from miguel_lm.config import AppConfig
from miguel_lm.remote import RemoteClientRuntime


def _wav_bytes(samples, sample_rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_remote_answer_decodes_backend_audio(monkeypatch):
    wav_payload = _wav_bytes([0, 1000, -1000, 0])
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return json.dumps(
                {
                    "provider": "remote",
                    "response": {"spoken_text": "Fine. Test the tiny loop first.", "emotion": "normal"},
                    "audio_wav_base64": base64.b64encode(wav_payload).decode("ascii"),
                    "sample_rate": 24000,
                    "audio_provider": "local_http_tts",
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append(
            (
                request.full_url,
                json.loads(request.data.decode("utf-8")),
                request.get_header("User-agent"),
            )
        )
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    runtime = RemoteClientRuntime(AppConfig.load("config/dev.yaml"))

    response = await runtime.answer("hello")
    clip = await runtime.synthesize(response.spoken_text)

    assert response.spoken_text == "Fine. Test the tiny loop first."
    assert clip.provider == "local_http_tts"
    assert requests[0][0] == "https://miguellm.miguelvasco.com/chat"
    assert requests[0][1] == {"text": "hello"}
    assert requests[0][2] == "MiguelLM/0.1.0"


@pytest.mark.asyncio
async def test_remote_metadata_comes_from_server(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return json.dumps(
                {
                    "app": {
                        "name": "MiguelLM",
                        "subtitle": "lab terminal",
                        "intro_text": "Server-provided intro.",
                        "assistant_label": "MiguelLM",
                        "status_label": "MIGUELLM",
                        "voice_test_text": "Server voice test.",
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    runtime = RemoteClientRuntime(AppConfig.load("config/dev.yaml"))

    metadata = await runtime.refresh_metadata()

    assert requests == ["https://miguellm.miguelvasco.com/metadata"]
    assert metadata.app_name == "MiguelLM"
    assert metadata.intro_text == "Server-provided intro."
    assert metadata.voice_test_text == "Server voice test."
