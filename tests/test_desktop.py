from miguel_lm.desktop import MiguelLMApi


class FakeRuntime:
    def metadata_dict(self):
        return {"app": {"name": "MiguelLM"}, "boot_lines": ["BOOT"], "has_avatars": True}

    def chat_payload(self, text):
        return {
            "response": {"spoken_text": "hi there", "emotion": "happy"},
            "audio_wav_base64": "AAAA",
            "sample_rate": 24000,
        }

    def fetch_avatars(self):
        return {"normal": {"idle": "aWRsZQ==", "talking": "dGFsaw=="}}

    async def listen_once(self):
        return "  spoken words  "


def test_metadata_passthrough():
    meta = MiguelLMApi(FakeRuntime()).metadata()
    assert meta["app"]["name"] == "MiguelLM"
    assert meta["has_avatars"] is True
    assert meta["boot_lines"] == ["BOOT"]


def test_chat_returns_full_payload():
    data = MiguelLMApi(FakeRuntime()).chat("hello")
    assert data["response"]["spoken_text"] == "hi there"
    assert data["response"]["emotion"] == "happy"
    assert data["audio_wav_base64"] == "AAAA"


def test_chat_rejects_empty():
    assert "error" in MiguelLMApi(FakeRuntime()).chat("   ")


def test_avatars_passthrough():
    avatars = MiguelLMApi(FakeRuntime()).avatars()
    assert avatars["normal"]["idle"] == "aWRsZQ=="
    assert avatars["normal"]["talking"] == "dGFsaw=="


def test_avatars_empty_on_error():
    class Boom:
        def fetch_avatars(self):
            raise RuntimeError("backend down")

    assert MiguelLMApi(Boom()).avatars() == {}


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
