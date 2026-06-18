from __future__ import annotations

from typing import Optional

from miguel_lm.config import AppConfig
from miguel_lm.providers.base import DialogueProvider, STTProvider, TTSProvider
from miguel_lm.providers.fallback import RuleBasedDialogueProvider
from miguel_lm.providers.local_http_tts_provider import LocalHttpTTSProvider
from miguel_lm.providers.local_model import OllamaDialogueProvider
from miguel_lm.providers.openai_provider import OpenAIDialogueProvider, OpenAISTTProvider


def build_dialogue_provider(config: AppConfig) -> DialogueProvider:
    dialogue = config.providers.dialogue or {}
    primary = dialogue.get("primary", "local_rule_based")
    if primary == "openai":
        openai_config = dialogue.get("openai") or {}
        return OpenAIDialogueProvider(
            api_key_env=openai_config.get("api_key_env", "OPENAI_API_KEY"),
            model_env=openai_config.get("model_env", "OPENAI_DIALOGUE_MODEL"),
            default_model=openai_config.get("default_model", "gpt-5.4-mini"),
            reasoning_effort=openai_config.get("reasoning_effort"),
        )
    if primary == "ollama":
        local_config = dialogue.get("local") or {}
        return OllamaDialogueProvider(
            endpoint=local_config.get("endpoint", "http://127.0.0.1:11434/api/generate"),
            model=local_config.get("model", "llama3.2:3b"),
        )
    return RuleBasedDialogueProvider()


def build_tts_provider(config: AppConfig) -> Optional[TTSProvider]:
    if config.voice.provider == "local_http":
        local_config = dict(getattr(config.voice, "local_http", {}) or {})
        return LocalHttpTTSProvider(
            endpoint_env=local_config.get("endpoint_env", "LOCAL_TTS_ENDPOINT"),
            default_endpoint=local_config.get("default_endpoint", "http://127.0.0.1:7861/synthesize"),
            sample_rate=config.voice.sample_rate,
            timeout_seconds=float(local_config.get("timeout_seconds", 120)),
            ref_audio=local_config.get("ref_audio"),
            ref_text=local_config.get("ref_text"),
            speed=_optional_float(local_config.get("speed")),
            nfe_step=_optional_int(local_config.get("nfe_step")),
        )
    return None


def build_stt_provider(config: AppConfig) -> Optional[STTProvider]:
    transcribe = config.input_audio.transcribe or {}
    if transcribe.get("provider", "openai") != "openai":
        return None
    return OpenAISTTProvider(
        api_key_env=transcribe.get("api_key_env", "OPENAI_API_KEY"),
        model_env=transcribe.get("model_env", "OPENAI_TRANSCRIBE_MODEL"),
        default_model=transcribe.get("default_model", "whisper-1"),
        prompt=transcribe.get("prompt", ""),
    )


def _optional_float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _optional_int(value) -> Optional[int]:
    return int(value) if value is not None else None
