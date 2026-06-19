"""Tests for the remote-client helpers used by the desktop app bridge."""
import json
import urllib.error
import urllib.request

import pytest

from miguel_lm.config import AppConfig
from miguel_lm.remote import RemoteClientRuntime


def _fake_json_response(payload):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return FakeResponse()


def test_metadata_dict_and_boot_lines(monkeypatch):
    payload = {
        "app": {"name": "MiguelLM", "intro_text": "hi"},
        "boot_lines": ["L1", "L2"],
        "has_head": True,
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _fake_json_response(payload))
    runtime = RemoteClientRuntime(AppConfig.load("config/dev.yaml"))

    assert runtime.metadata_dict() == payload
    meta = runtime._metadata.from_mapping(payload, runtime.metadata)
    assert meta.boot_lines == ["L1", "L2"]
    assert meta.has_head is True


def test_chat_payload_returns_raw_dict(monkeypatch):
    payload = {"response": {"spoken_text": "hey", "emotion": "warm"}, "audio_wav_base64": "QQ=="}
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _fake_json_response(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    runtime = RemoteClientRuntime(AppConfig.load("config/dev.yaml"))

    assert runtime.chat_payload("hello") == payload
    assert captured["url"].endswith("/chat")
    assert captured["body"] == {"text": "hello"}


def test_fetch_head_model_returns_bytes(monkeypatch):
    class FakeBinary:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def read(self):
            return b"GLBDATA"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeBinary())
    runtime = RemoteClientRuntime(AppConfig.load("config/dev.yaml"))
    assert runtime.fetch_head_model() == b"GLBDATA"


def test_fetch_head_model_none_on_404(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "no head", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    runtime = RemoteClientRuntime(AppConfig.load("config/dev.yaml"))
    assert runtime.fetch_head_model() is None
