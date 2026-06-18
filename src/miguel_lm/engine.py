from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional

from miguel_lm.audio_input import FfmpegAudioRecorder, PushToTalkInput
from miguel_lm.config import AppConfig
from miguel_lm.memory import (
    MemoryStore,
    PrivacyConsentStore,
    TranscriptStore,
    extract_simple_memory_candidates,
)
from miguel_lm.models import AudioClip, ConversationTurn, DialogueResponse
from miguel_lm.persona import PersonaPack
from miguel_lm.playback import AudioPlayer
from miguel_lm.providers import build_dialogue_provider, build_stt_provider, build_tts_provider
from miguel_lm.providers.base import DialogueProvider, STTProvider, TTSProvider
from miguel_lm.providers.local_http_tts_provider import LocalHttpTTSProvider
from miguel_lm.safety import apply_response_safety


class ConversationEngine:
    def __init__(
        self,
        persona: PersonaPack,
        memory_store: MemoryStore,
        dialogue_provider: DialogueProvider,
        transcript_store: Optional[TranscriptStore] = None,
    ) -> None:
        self.persona = persona
        self.memory_store = memory_store
        self.dialogue_provider = dialogue_provider
        self.transcript_store = transcript_store
        self.history: List[ConversationTurn] = []
        self.pending_memory_candidates = []
        self.pending_source_ids: List[str] = []

    async def answer(self, user_text: str) -> DialogueResponse:
        user_turn = ConversationTurn(role="user", content=user_text)
        self.history.append(user_turn)
        if self.transcript_store:
            self.transcript_store.append_turn(user_turn)
        relevant_memories = self.memory_store.search(user_text)
        prompt = self.persona.render_system_prompt((record.text for record in relevant_memories))
        response = await self.dialogue_provider.respond(prompt, self.history, user_text, relevant_memories)
        response = apply_response_safety(user_text, response)
        assistant_turn = ConversationTurn(
            role="assistant",
            content=response.spoken_text,
            metadata={"emotion": response.emotion, "provider": response.provider},
        )
        self.history.append(assistant_turn)
        if self.transcript_store:
            self.transcript_store.append_turn(assistant_turn)
        self.pending_memory_candidates.extend(response.memory_candidates)
        self.pending_source_ids.append(user_turn.turn_id)
        return response

    def finalize_memory(self) -> int:
        candidates = list(self.pending_memory_candidates)
        candidates.extend(extract_simple_memory_candidates(self.history))
        records = self.memory_store.store_candidates(candidates, self.pending_source_ids)
        self.pending_memory_candidates.clear()
        self.pending_source_ids.clear()
        return len(records)


@dataclass
class RuntimeStatus:
    tts_provider: str
    tts_endpoint: str
    tts_healthy: bool
    memory_enabled: bool
    player: Optional[str]


class MiguelLMRuntime:
    def __init__(
        self,
        config: AppConfig,
        engine: ConversationEngine,
        memory_store: MemoryStore,
        consent_store: PrivacyConsentStore,
        tts_provider: Optional[TTSProvider],
        stt_provider: Optional[STTProvider],
        player: AudioPlayer,
    ) -> None:
        self.config = config
        self.engine = engine
        self.memory_store = memory_store
        self.consent_store = consent_store
        self.tts_provider = tts_provider
        self.stt_provider = stt_provider
        self.player = player
        self._ptt: Optional[PushToTalkInput] = None

    @classmethod
    def build(cls, config: AppConfig) -> "MiguelLMRuntime":
        persona = PersonaPack.load(config.resolve_persona_dir())
        consent_store = PrivacyConsentStore(config.resolve(config.paths.consent_file))
        memory_store = MemoryStore(config.resolve(config.paths.memory_dir), config.memory, consent_store)
        transcript_store = TranscriptStore(config.resolve(config.paths.sessions_dir))
        dialogue_provider = build_dialogue_provider(config)
        engine = ConversationEngine(persona, memory_store, dialogue_provider, transcript_store)
        tts_provider = build_tts_provider(config)
        stt_provider = build_stt_provider(config)
        player = AudioPlayer(config.playback, config.resolve("tmp"))
        return cls(config, engine, memory_store, consent_store, tts_provider, stt_provider, player)

    def status(self) -> RuntimeStatus:
        endpoint = getattr(self.tts_provider, "endpoint", "")
        healthy = False
        if isinstance(self.tts_provider, LocalHttpTTSProvider):
            healthy = self.tts_provider.healthy(timeout=1.5)
        return RuntimeStatus(
            tts_provider=getattr(self.tts_provider, "name", "none") if self.tts_provider else "none",
            tts_endpoint=endpoint,
            tts_healthy=healthy,
            memory_enabled=self.memory_store.memory_allowed(),
            player=self.player.available_player(),
        )

    async def answer(self, user_text: str) -> DialogueResponse:
        response = await self.engine.answer(user_text)
        self.engine.finalize_memory()
        return response

    async def synthesize(self, text: str) -> Optional[AudioClip]:
        if not self.tts_provider:
            return None
        return await self.tts_provider.synthesize(text)

    async def speak(self, text: str) -> Optional[str]:
        clip = await self.synthesize(text)
        if clip is None:
            return None
        path = await self.player.play(clip)
        return str(path)

    async def listen_once(self) -> str:
        if self.stt_provider is None:
            raise RuntimeError("Speech input requires a configured STT provider.")
        if self._ptt is None:
            recorder = FfmpegAudioRecorder(self.config.input_audio)
            self._ptt = await PushToTalkInput(recorder, self.stt_provider).__aenter__()
        return await self._ptt.listen_once()

    async def close(self) -> None:
        if self._ptt is not None:
            await self._ptt.__aexit__(None, None, None)
            self._ptt = None

    def set_memory_enabled(self, enabled: bool) -> bool:
        self.consent_store.set_memory_enabled(enabled)
        return self.memory_store.memory_allowed()

    def memory_summary(self) -> List[str]:
        rows = []
        for record in self.memory_store.list_records():
            rows.append("%s  %s" % (record.memory_id, record.text))
        return rows

    def delete_memory(self, memory_id: str) -> bool:
        return self.memory_store.delete(memory_id)

    def clear_memory(self) -> int:
        return self.memory_store.clear()

    async def speak_background(self, text: str) -> Optional[str]:
        return await asyncio.create_task(self.speak(text))
