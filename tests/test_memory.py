from pathlib import Path

from miguel_lm.config import MemorySettings
from miguel_lm.memory import MemoryStore, PrivacyConsentStore


def test_memory_requires_local_consent(tmp_path: Path):
    consent = PrivacyConsentStore(tmp_path / "consent.json")
    store = MemoryStore(tmp_path / "memory", MemorySettings(require_consent=True), consent)

    assert store.add_memory("Ana likes short demos", ["turn_1"], 0.8) is None
    assert store.list_records() == []

    consent.set_memory_enabled(True)
    record = store.add_memory("Ana likes short demos", ["turn_1"], 0.8)

    assert record is not None
    assert store.list_records()[0].text == "Ana likes short demos"


def test_memory_redacts_sensitive_text(tmp_path: Path):
    consent = PrivacyConsentStore(tmp_path / "consent.json")
    consent.set_memory_enabled(True)
    store = MemoryStore(tmp_path / "memory", MemorySettings(require_consent=True), consent)

    record = store.add_memory("Miguel email is miguel@example.com", ["turn_1"], 0.8)

    assert record is not None
    assert "[REDACTED]" in record.text
    assert record.redacted is True
