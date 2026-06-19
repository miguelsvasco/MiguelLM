import base64

from miguel_lm.desktop import MiguelLMApi


class FakeRuntime:
    def metadata_dict(self):
        return {"app": {"name": "MiguelLM"}, "boot_lines": ["BOOT"], "has_head": False}

    def chat_payload(self, text):
        return {
            "response": {"spoken_text": "hi there", "emotion": "amused"},
            "audio_wav_base64": "AAAA",
            "sample_rate": 24000,
        }

    def fetch_head_model(self):
        return b"GLB-BYTES"

    async def listen_once(self):
        return "  spoken words  "


def test_metadata_passthrough():
    meta = MiguelLMApi(FakeRuntime()).metadata()
    assert meta["app"]["name"] == "MiguelLM"
    assert meta["has_head"] is False
    assert meta["boot_lines"] == ["BOOT"]


def test_chat_returns_full_payload():
    data = MiguelLMApi(FakeRuntime()).chat("hello")
    assert data["response"]["spoken_text"] == "hi there"
    assert data["response"]["emotion"] == "amused"
    assert data["audio_wav_base64"] == "AAAA"


def test_chat_rejects_empty():
    assert "error" in MiguelLMApi(FakeRuntime()).chat("   ")


def test_head_model_b64_roundtrips():
    b64 = MiguelLMApi(FakeRuntime()).head_model_b64()
    assert base64.b64decode(b64) == b"GLB-BYTES"


def test_listen_returns_trimmed_transcript():
    assert MiguelLMApi(FakeRuntime()).listen() == {"text": "spoken words"}


def test_errors_become_error_dicts():
    class Boom:
        def metadata_dict(self):
            raise RuntimeError("backend down")

        def chat_payload(self, text):
            raise RuntimeError("backend down")

    api = MiguelLMApi(Boom())
    assert "error" in api.metadata()
    assert "error" in api.chat("hi")
