from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from miguel_lm.config import MemorySettings
from miguel_lm.models import ConversationTurn, MemoryRecord, new_id, utc_now


SENSITIVE_PATTERNS = [
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"),
    re.compile(r"\b(?:api[_-]?key|token|password|secret)\s*(?:is|=|:)\s*\S+", re.IGNORECASE),
]


def redact_sensitive_text(text: str) -> Tuple[str, bool]:
    redacted = False
    output = text
    for pattern in SENSITIVE_PATTERNS:
        output, count = pattern.subn("[REDACTED]", output)
        redacted = redacted or count > 0
    return output, redacted


@dataclass
class PrivacyConsent:
    memory_enabled: bool = False
    acknowledged_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PrivacyConsent":
        return cls(
            memory_enabled=bool(data.get("memory_enabled", False)),
            acknowledged_at=data.get("acknowledged_at"),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_enabled": self.memory_enabled,
            "acknowledged_at": self.acknowledged_at,
            "updated_at": self.updated_at,
        }


class PrivacyConsentStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> PrivacyConsent:
        if not self.path.exists():
            return PrivacyConsent()
        try:
            return PrivacyConsent.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            return PrivacyConsent()

    def save(self, consent: PrivacyConsent) -> None:
        now = utc_now()
        if consent.acknowledged_at is None:
            consent.acknowledged_at = now
        consent.updated_at = now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(consent.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def set_memory_enabled(self, enabled: bool) -> PrivacyConsent:
        consent = self.load()
        consent.memory_enabled = enabled
        self.save(consent)
        return consent


class MemoryStore:
    def __init__(self, directory: Path, settings: MemorySettings, consent_store: Optional[PrivacyConsentStore] = None) -> None:
        self.directory = directory
        self.settings = settings
        self.consent_store = consent_store
        self.active_path = directory / "active.jsonl"

    def memory_allowed(self) -> bool:
        if not self.settings.enabled or not self.settings.auto_write:
            return False
        if self.settings.require_consent:
            if self.consent_store is None:
                return False
            return self.consent_store.load().memory_enabled
        return True

    def ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.active_path.touch(exist_ok=True)

    def list_records(self, include_disabled: bool = False) -> List[MemoryRecord]:
        if not self.active_path.exists():
            return []
        records = []
        with self.active_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = MemoryRecord.from_dict(json.loads(line))
                if include_disabled or not record.disabled:
                    records.append(record)
        return records

    def add_memory(
        self,
        text: str,
        source_utterance_ids: Iterable[str],
        confidence: float,
        topic: str = "conversation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryRecord]:
        if not self.memory_allowed():
            return None
        if confidence < self.settings.min_confidence:
            return None
        clean_text = text.strip()
        if not clean_text:
            return None
        was_redacted = False
        if self.settings.redact_sensitive:
            clean_text, was_redacted = redact_sensitive_text(clean_text)
        if clean_text == "[REDACTED]":
            return None
        self.ensure()
        record = MemoryRecord(
            text=clean_text,
            source_utterance_ids=list(source_utterance_ids),
            confidence=confidence,
            topic=topic,
            redacted=was_redacted,
            metadata=metadata or {},
        )
        with self.active_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        return record

    def store_candidates(
        self,
        candidates: Iterable[Dict[str, Any]],
        source_utterance_ids: Iterable[str],
    ) -> List[MemoryRecord]:
        stored = []
        for candidate in candidates:
            if len(stored) >= self.settings.max_memories_per_session:
                break
            if isinstance(candidate, str):
                candidate = {"text": candidate, "confidence": 0.6, "topic": "conversation"}
            if not isinstance(candidate, dict):
                continue
            record = self.add_memory(
                text=str(candidate.get("text") or ""),
                source_utterance_ids=source_utterance_ids,
                confidence=float(candidate.get("confidence", 0.0)),
                topic=str(candidate.get("topic") or "conversation"),
                metadata={"source": "auto_candidate"},
            )
            if record:
                stored.append(record)
        return stored

    def search(self, query: str, limit: int = 6) -> List[MemoryRecord]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored = []
        for record in self.list_records():
            score = len(query_tokens.intersection(_tokens(record.text)))
            if score:
                scored.append((score, record.created_at, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [record for _, _, record in scored[:limit]]

    def disable(self, memory_id: str) -> bool:
        records = self.list_records(include_disabled=True)
        changed = False
        for record in records:
            if record.memory_id == memory_id:
                record.disabled = True
                changed = True
        if changed:
            self._write_all(records)
        return changed

    def delete(self, memory_id: str) -> bool:
        records = self.list_records(include_disabled=True)
        kept = [record for record in records if record.memory_id != memory_id]
        if len(kept) == len(records):
            return False
        self._write_all(kept)
        return True

    def clear(self) -> int:
        records = self.list_records(include_disabled=True)
        self._write_all([])
        return len(records)

    def _write_all(self, records: Iterable[MemoryRecord]) -> None:
        self.ensure()
        with self.active_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


class TranscriptStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.session_id = new_id("session")
        self.path = self.directory / ("%s.jsonl" % self.session_id)

    def ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.ensure()
        event = {
            "event_id": new_id("evt"),
            "session_id": self.session_id,
            "created_at": utc_now(),
            "type": event_type,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def append_turn(self, turn: ConversationTurn) -> None:
        self.append("conversation.turn", turn.to_dict())

    @staticmethod
    def load(path: Path) -> List[Dict[str, Any]]:
        events = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    events.append(json.loads(line))
        return events


def extract_simple_memory_candidates(turns: Iterable[ConversationTurn]) -> List[Dict[str, Any]]:
    candidates = []
    for turn in turns:
        if turn.role != "user":
            continue
        text = turn.content.strip()
        lowered = text.lower()
        if lowered.startswith("remember that "):
            candidates.append(
                {
                    "text": text[len("remember that ") :].strip(),
                    "confidence": 0.75,
                    "topic": "explicit_user_memory",
                }
            )
        elif "my name is " in lowered:
            candidates.append({"text": text, "confidence": 0.6, "topic": "visitor_profile"})
    return candidates


def _tokens(text: str) -> set:
    return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(token) > 2}
