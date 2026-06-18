from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


REQUIRED_PERSONA_FILES = [
    "identity.md",
    "speaking_style.md",
    "lab_knowledge.md",
    "research_projects.md",
    "boundaries.md",
    "facts_to_remember.md",
]


@dataclass
class PersonaDocument:
    name: str
    path: Path
    text: str


class PersonaValidationError(RuntimeError):
    pass


class PersonaPack:
    def __init__(self, directory: Path, documents: Sequence[PersonaDocument]) -> None:
        self.directory = directory
        self.documents = list(documents)

    @classmethod
    def load(cls, directory: Path) -> "PersonaPack":
        if not directory.exists():
            raise PersonaValidationError("Persona directory does not exist: %s" % directory)
        all_paths = {path.name: path for path in directory.glob("*.md")}
        ordered_paths: List[Path] = []
        for name in REQUIRED_PERSONA_FILES:
            if name in all_paths:
                ordered_paths.append(all_paths[name])
        for path in sorted(directory.glob("*.md")):
            if path not in ordered_paths:
                ordered_paths.append(path)
        documents = [
            PersonaDocument(path.name, path, path.read_text(encoding="utf-8").strip())
            for path in ordered_paths
        ]
        pack = cls(directory, documents)
        pack.validate()
        return pack

    def validate(self) -> None:
        found = {doc.name for doc in self.documents}
        missing = [name for name in REQUIRED_PERSONA_FILES if name not in found]
        if missing:
            raise PersonaValidationError("Missing persona files: %s" % ", ".join(missing))
        empty = [doc.name for doc in self.documents if not doc.text.strip()]
        if empty:
            raise PersonaValidationError("Empty persona files: %s" % ", ".join(empty))

    def render_system_prompt(self, memories: Iterable[str] = ()) -> str:
        parts = [
            "You are MiguelLM, a standalone terminal clone of Miguel.",
            "This is a live terminal conversation. Keep spoken_text short and natural, "
            "usually one or two compact paragraphs at most. Do not lecture unless asked.",
            "spoken_text is exactly what you say. Do not include stage directions, hidden reasoning, "
            "JSON explanations, or descriptions of your own plan.",
            "You are a familiar friend and colleague, not a generic assistant. Do not open with "
            "'how can I help'. React directly, be dry and warm, and ask a pointed follow-up when useful.",
            "Return compact JSON with these keys: spoken_text, emotion, memory_candidates, safety_flags.",
            "Allowed emotions: warm, amused, confused, serious, speaking.",
            "Use memory_candidates only for durable, non-sensitive facts worth remembering.",
            "Never store secrets, contact data, health data, credentials, or third-party private information.",
            "",
            "Persona pack:",
        ]
        for doc in self.documents:
            parts.append("\n--- %s ---\n%s" % (doc.name, doc.text))
        memory_list = [item.strip() for item in memories if item and item.strip()]
        if memory_list:
            parts.append("\n--- approved automatic memories ---")
            for item in memory_list:
                parts.append("- %s" % item)
        return "\n".join(parts).strip()

    def search_context(self, query: str, limit: int = 6) -> List[str]:
        tokens = _tokens(query)
        if not tokens:
            return []
        chunks = []
        for doc in self.documents:
            for chunk in _split_markdown(doc.text):
                score = len(tokens.intersection(_tokens(chunk)))
                if score:
                    chunks.append((score, doc.name, chunk))
        chunks.sort(key=lambda item: (-item[0], item[1]))
        return [chunk for _, _, chunk in chunks[:limit]]


def _tokens(text: str) -> set:
    return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(token) > 2}


def _split_markdown(text: str) -> List[str]:
    pieces = re.split(r"\n(?=#+\s)", text)
    return [piece.strip() for piece in pieces if piece.strip()]
