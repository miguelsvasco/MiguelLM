from __future__ import annotations

import os
from typing import Iterable, List, Optional

from miguel_lm.models import AudioClip, ConversationTurn, DialogueResponse, MemoryRecord
from miguel_lm.providers.fallback import RuleBasedDialogueProvider
from miguel_lm.providers.parsing import parse_dialogue_json


class OpenAIDialogueProvider:
    name = "openai"

    def __init__(
        self,
        api_key_env: str,
        model_env: str,
        default_model: str,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        self.api_key_env = api_key_env
        self.model = os.environ.get(model_env) or default_model
        self.reasoning_effort = reasoning_effort
        self._client = None
        self.fallback = RuleBasedDialogueProvider()

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=os.environ.get(self.api_key_env))
        return self._client

    async def respond(
        self,
        system_prompt: str,
        history: List[ConversationTurn],
        user_text: str,
        memories: Iterable[MemoryRecord],
    ) -> DialogueResponse:
        if not os.environ.get(self.api_key_env):
            return await self.fallback.respond(system_prompt, history, user_text, memories)
        input_items = []
        for turn in history[-10:]:
            role = "assistant" if turn.role == "assistant" else "user"
            input_items.append({"role": role, "content": turn.content})
        input_items.append({"role": "user", "content": user_text})
        try:
            kwargs = {
                "model": self.model,
                "instructions": system_prompt,
                "input": input_items,
                "max_output_tokens": 900,
            }
            if self.reasoning_effort:
                kwargs["reasoning"] = {"effort": self.reasoning_effort}
            result = await self.client.responses.create(**kwargs)
            output_text = getattr(result, "output_text", None) or str(result)
            return parse_dialogue_json(output_text, provider=self.name)
        except Exception:
            return await self.fallback.respond(system_prompt, history, user_text, memories)


class OpenAISTTProvider:
    name = "openai_stt"

    def __init__(self, api_key_env: str, model_env: str, default_model: str, prompt: str = "") -> None:
        self.api_key_env = api_key_env
        self.model = os.environ.get(model_env) or default_model
        self.prompt = prompt
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=os.environ.get(self.api_key_env))
        return self._client

    async def transcribe_file(self, path: str) -> str:
        if not os.environ.get(self.api_key_env):
            raise RuntimeError("OpenAI API key is not configured for transcription.")
        with open(path, "rb") as audio_file:
            kwargs = {
                "model": self.model,
                "file": audio_file,
                "response_format": "text",
            }
            if self.prompt:
                kwargs["prompt"] = self.prompt
            result = await self.client.audio.transcriptions.create(**kwargs)
        if isinstance(result, str):
            return result.strip()
        return str(getattr(result, "text", result)).strip()


class DisabledTTSProvider:
    name = "disabled_tts"

    async def synthesize(self, text: str) -> AudioClip:
        raise RuntimeError("TTS is disabled.")
