from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid4().hex[:12])


@dataclass
class ConversationTurn:
    role: str
    content: str
    turn_id: str = field(default_factory=lambda: new_id("turn"))
    created_at: str = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "turn_id": self.turn_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class DialogueResponse:
    spoken_text: str
    emotion: str = "warm"
    memory_candidates: List[Dict[str, Any]] = field(default_factory=list)
    safety_flags: List[str] = field(default_factory=list)
    provider: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Dict[str, Any], provider: str = "unknown") -> "DialogueResponse":
        spoken = str(data.get("spoken_text") or data.get("text") or "").strip()
        memory_candidates = data.get("memory_candidates") or []
        if isinstance(memory_candidates, list):
            normalized = []
            for item in memory_candidates:
                if isinstance(item, str):
                    normalized.append({"text": item, "confidence": 0.6, "topic": "conversation"})
                elif isinstance(item, dict):
                    normalized.append(item)
            memory_candidates = normalized
        else:
            memory_candidates = []

        safety_flags = data.get("safety_flags") or []
        if not isinstance(safety_flags, list):
            safety_flags = [str(safety_flags)]

        return cls(
            spoken_text=spoken or "I am not sure how to answer that yet.",
            emotion=str(data.get("emotion") or "warm"),
            memory_candidates=memory_candidates,
            safety_flags=[str(flag) for flag in safety_flags],
            provider=provider,
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spoken_text": self.spoken_text,
            "emotion": self.emotion,
            "memory_candidates": self.memory_candidates,
            "safety_flags": self.safety_flags,
            "provider": self.provider,
        }


@dataclass
class AudioClip:
    pcm: bytes
    sample_rate: int
    text: str
    provider: str = "unknown"


@dataclass
class RuntimeStatus:
    tts_provider: str = "remote"
    tts_endpoint: str = ""
    tts_healthy: bool = False
    memory_enabled: bool = False
    player: str = ""


@dataclass
class ClientMetadata:
    app_name: str = "MiguelLM"
    subtitle: str = "remote terminal client"
    intro_text: str = "Connected to the remote chat service. Type a message and press Enter."
    assistant_label: str = "Assistant"
    status_label: str = "MIGUELLM"
    voice_test_text: str = "Voice test. If you hear this, remote speech playback is working."
    privacy_text: str = (
        "This client sends chat, optional microphone recordings, and memory commands to the configured "
        "remote service. Durable memory is off unless enabled with /memory on."
    )

    @classmethod
    def from_mapping(cls, data: Dict[str, Any], fallback: "ClientMetadata") -> "ClientMetadata":
        app = data.get("app") if isinstance(data.get("app"), dict) else data

        def text(name: str, default: str) -> str:
            value = app.get(name)
            return str(value).strip() if value is not None and str(value).strip() else default

        app_name = text("app_name", text("name", fallback.app_name))
        return cls(
            app_name=app_name,
            subtitle=text("subtitle", fallback.subtitle),
            intro_text=text("intro_text", fallback.intro_text),
            assistant_label=text("assistant_label", app_name if app_name else fallback.assistant_label),
            status_label=text("status_label", app_name.upper() if app_name else fallback.status_label),
            voice_test_text=text("voice_test_text", fallback.voice_test_text),
            privacy_text=text("privacy_text", fallback.privacy_text),
        )


@dataclass
class MemoryRecord:
    text: str
    source_utterance_ids: List[str]
    confidence: float
    topic: str = "conversation"
    memory_id: str = field(default_factory=lambda: new_id("mem"))
    created_at: str = field(default_factory=utc_now)
    disabled: bool = False
    redacted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        return cls(
            text=str(data.get("text") or ""),
            source_utterance_ids=[str(item) for item in data.get("source_utterance_ids", [])],
            confidence=float(data.get("confidence", 0.0)),
            topic=str(data.get("topic") or "conversation"),
            memory_id=str(data.get("memory_id") or data.get("id") or new_id("mem")),
            created_at=str(data.get("created_at") or utc_now()),
            disabled=bool(data.get("disabled", False)),
            redacted=bool(data.get("redacted", False)),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "text": self.text,
            "source_utterance_ids": self.source_utterance_ids,
            "confidence": self.confidence,
            "topic": self.topic,
            "created_at": self.created_at,
            "disabled": self.disabled,
            "redacted": self.redacted,
            "metadata": self.metadata,
        }
