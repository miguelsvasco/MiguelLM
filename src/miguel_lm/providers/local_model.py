from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Iterable, List

from miguel_lm.models import ConversationTurn, DialogueResponse, MemoryRecord
from miguel_lm.providers.fallback import RuleBasedDialogueProvider
from miguel_lm.providers.parsing import parse_dialogue_json


class OllamaDialogueProvider:
    name = "ollama"

    def __init__(self, endpoint: str, model: str, timeout_seconds: float = 60.0) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback = RuleBasedDialogueProvider()

    async def respond(
        self,
        system_prompt: str,
        history: List[ConversationTurn],
        user_text: str,
        memories: Iterable[MemoryRecord],
    ) -> DialogueResponse:
        prompt = self._prompt(system_prompt, history, user_text)
        try:
            text = await asyncio.to_thread(self._generate_blocking, prompt)
            return parse_dialogue_json(text, provider=self.name)
        except Exception:
            return await self.fallback.respond(system_prompt, history, user_text, memories)

    def _prompt(self, system_prompt: str, history: List[ConversationTurn], user_text: str) -> str:
        lines = [system_prompt, "", "Recent conversation:"]
        for turn in history[-8:]:
            lines.append("%s: %s" % (turn.role, turn.content))
        lines.append("user: %s" % user_text)
        lines.append("Return JSON only.")
        return "\n".join(lines)

    def _generate_blocking(self, prompt: str) -> str:
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("response") or "")
