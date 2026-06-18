import pytest

from miguel_lm.config import MemorySettings
from miguel_lm.engine import ConversationEngine
from miguel_lm.memory import MemoryStore, PrivacyConsentStore
from miguel_lm.persona import PersonaPack
from miguel_lm.providers.fallback import RuleBasedDialogueProvider


@pytest.mark.asyncio
async def test_engine_answers_and_finalizes_memory(tmp_path):
    consent = PrivacyConsentStore(tmp_path / "consent.json")
    consent.set_memory_enabled(True)
    persona = PersonaPack.load(__import__("pathlib").Path("persona"))
    store = MemoryStore(tmp_path / "memory", MemorySettings(require_consent=True), consent)
    engine = ConversationEngine(persona, store, RuleBasedDialogueProvider())

    response = await engine.answer("remember that Ana likes short robotics demos")
    stored_count = engine.finalize_memory()

    assert "keep that" in response.spoken_text
    assert stored_count >= 1
    assert any("Ana likes short robotics demos" in record.text for record in store.list_records())
