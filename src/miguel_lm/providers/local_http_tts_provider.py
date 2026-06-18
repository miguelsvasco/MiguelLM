from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from miguel_lm.audio_codec import wav_bytes_to_pcm16_mono
from miguel_lm.models import AudioClip


class LocalHttpTTSProvider:
    name = "local_http_tts"

    def __init__(
        self,
        endpoint_env: str,
        default_endpoint: str,
        sample_rate: int,
        timeout_seconds: float = 120.0,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        speed: Optional[float] = None,
        nfe_step: Optional[int] = None,
    ) -> None:
        self.endpoint_env = endpoint_env
        self.default_endpoint = default_endpoint
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds
        self.ref_audio = ref_audio or None
        self.ref_text = ref_text or None
        self.speed = speed
        self.nfe_step = nfe_step

    @property
    def endpoint(self) -> str:
        return os.environ.get(self.endpoint_env) or self.default_endpoint

    @property
    def health_url(self) -> str:
        parts = urlsplit(self.endpoint)
        return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))

    def healthy(self, timeout: float = 5.0) -> bool:
        try:
            with urllib.request.urlopen(self.health_url, timeout=timeout) as response:
                return 200 <= response.status < 300
        except Exception:
            return False

    async def synthesize(
        self, text: str, speed: Optional[float] = None, nfe_step: Optional[int] = None
    ) -> AudioClip:
        wav_bytes = await asyncio.to_thread(self._synthesize_blocking, text, speed, nfe_step)
        pcm = wav_bytes_to_pcm16_mono(wav_bytes, self.sample_rate)
        return AudioClip(pcm=pcm, sample_rate=self.sample_rate, text=text, provider=self.name)

    def _synthesize_blocking(
        self, text: str, speed: Optional[float] = None, nfe_step: Optional[int] = None
    ) -> bytes:
        payload: Dict[str, Any] = {"text": text}
        if self.ref_audio:
            payload["ref_audio"] = self.ref_audio
        if self.ref_text:
            payload["ref_text"] = self.ref_text
        effective_speed = speed if speed is not None else self.speed
        if effective_speed is not None:
            payload["speed"] = effective_speed
        effective_nfe = nfe_step if nfe_step is not None else self.nfe_step
        if effective_nfe is not None:
            payload["nfe_step"] = effective_nfe
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("Local TTS failed: HTTP %s %s" % (exc.code, details)) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Local TTS server is not reachable at %s: %s" % (self.endpoint, exc.reason)) from exc
        if "audio" not in content_type and not body.startswith(b"RIFF"):
            raise RuntimeError("Local TTS returned non-audio response: %s" % body[:200].decode("utf-8", errors="replace"))
        return body
