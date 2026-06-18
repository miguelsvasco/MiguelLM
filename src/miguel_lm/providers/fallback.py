from __future__ import annotations

from typing import Iterable, List

from miguel_lm.models import ConversationTurn, DialogueResponse, MemoryRecord


class RuleBasedDialogueProvider:
    name = "local_rule_based"

    async def respond(
        self,
        system_prompt: str,
        history: List[ConversationTurn],
        user_text: str,
        memories: Iterable[MemoryRecord],
    ) -> DialogueResponse:
        lowered = user_text.lower()
        memory_list = list(memories)
        if "remember that" in lowered:
            spoken = "Fine, I will keep that as a possible memory, assuming it is not secret nonsense."
            candidates = [
                {
                    "text": user_text.split("remember that", 1)[-1].strip(),
                    "confidence": 0.72,
                    "topic": "explicit_user_memory",
                }
            ]
        elif any(word in lowered for word in ["hello", "hi", "hey"]):
            spoken = "Hello. I am MiguelLM, the terminal clone. This is weird, but apparently useful."
            candidates = []
        elif "project" in lowered or "robot" in lowered or "research" in lowered:
            spoken = (
                "Start with the smallest loop that can fail clearly: input, behavior, output, and one measurement. "
                "Then we can argue about whether the idea is good."
            )
            candidates = []
        elif memory_list:
            spoken = "From what I remember, %s. Check it against reality before building a shrine to it." % memory_list[0].text
            candidates = []
        else:
            spoken = (
                "I do not have a specific note for that yet. Make the assumption explicit, test the smallest thing, "
                "and write down what changed. Annoying, yes. Effective, also yes."
            )
            candidates = []
        return DialogueResponse(
            spoken_text=spoken,
            emotion="warm",
            memory_candidates=candidates,
            provider=self.name,
        )
