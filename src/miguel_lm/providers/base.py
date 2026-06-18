from __future__ import annotations

from typing import Iterable, List, Protocol

from miguel_lm.models import AudioClip, ConversationTurn, DialogueResponse, MemoryRecord


class DialogueProvider(Protocol):
    async def respond(
        self,
        system_prompt: str,
        history: List[ConversationTurn],
        user_text: str,
        memories: Iterable[MemoryRecord],
    ) -> DialogueResponse:
        ...


class TTSProvider(Protocol):
    async def synthesize(self, text: str) -> AudioClip:
        ...


class STTProvider(Protocol):
    async def transcribe_file(self, path: str) -> str:
        ...
