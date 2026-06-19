from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from miguel_lm.audio_codec import wav_bytes_to_pcm16_mono
from miguel_lm.audio_input import FfmpegAudioRecorder, PushToTalkInput
from miguel_lm.config import AppConfig
from miguel_lm.models import AudioClip, ClientMetadata, DialogueResponse, RuntimeStatus
from miguel_lm.playback import AudioPlayer
from miguel_lm import __version__


class RemoteServiceError(RuntimeError):
    pass


class RemoteClientRuntime:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.url = config.backend.resolved_url.rstrip("/")
        self.token = config.backend.client_token
        self.timeout_seconds = config.backend.timeout_seconds
        self.player = AudioPlayer(config.playback, config.resolve(config.paths.tmp_dir))
        self._ptt: Optional[PushToTalkInput] = None
        self._audio_cache: Dict[str, AudioClip] = {}
        default_metadata = ClientMetadata()
        self._metadata = ClientMetadata(
            app_name=config.app_name,
            intro_text=config.intro_text or default_metadata.intro_text,
        )

    @property
    def metadata(self) -> ClientMetadata:
        return self._metadata

    async def refresh_metadata(self) -> ClientMetadata:
        data = await _run_blocking(
            self._request_json,
            "GET",
            "/metadata",
            None,
            True,
            True,
            2.5,
        )
        if not data:
            data = await _run_blocking(
                self._request_json,
                "GET",
                "/health",
                None,
                False,
                True,
                1.5,
            )
        if data:
            self._metadata = ClientMetadata.from_mapping(data, self._metadata)
        return self._metadata

    def status(self) -> RuntimeStatus:
        health = self._request_json("GET", "/health", auth=False, tolerate_errors=True, timeout_seconds=1.5) or {}
        return RuntimeStatus(
            tts_provider=str(health.get("tts_provider") or "remote"),
            tts_endpoint=self.url,
            tts_healthy=bool(health.get("tts_healthy", False)),
            memory_enabled=bool(health.get("memory_enabled", False)),
            player=self.player.available_player(),
        )

    async def answer(self, user_text: str) -> DialogueResponse:
        data = await _run_blocking(self._request_json, "POST", "/chat", {"text": user_text})
        response = DialogueResponse.from_mapping(data.get("response") or data, provider=str(data.get("provider") or "remote"))
        clip = _clip_from_response_audio(data, response.spoken_text)
        if clip is not None:
            self._audio_cache[response.spoken_text] = clip
        return response

    async def synthesize(self, text: str) -> Optional[AudioClip]:
        if text in self._audio_cache:
            return self._audio_cache.pop(text)
        data = await _run_blocking(self._request_json, "POST", "/synthesize", {"text": text})
        clip = _clip_from_response_audio(data, text)
        if clip is None:
            raise RemoteServiceError(str(data.get("audio_error") or "Remote service returned no audio."))
        return clip

    async def speak(self, text: str) -> Optional[str]:
        clip = await self.synthesize(text)
        if clip is None:
            return None
        path = await self.player.play(clip)
        return str(path)

    async def listen_once(self) -> str:
        recorder = FfmpegAudioRecorder(self.config.input_audio)
        if self._ptt is None:
            self._ptt = await _RemotePushToTalk(recorder, self).__aenter__()
        return await self._ptt.listen_once()

    async def close(self) -> None:
        if self._ptt is not None:
            await self._ptt.__aexit__(None, None, None)
            self._ptt = None

    def set_memory_enabled(self, enabled: bool) -> bool:
        data = self._request_json("POST", "/memory", {"enabled": enabled})
        return bool(data.get("memory_enabled", False))

    def memory_summary(self) -> List[str]:
        data = self._request_json("GET", "/memory")
        rows = []
        for record in data.get("memories") or []:
            rows.append("%s  %s" % (record.get("memory_id"), record.get("text")))
        return rows

    def delete_memory(self, memory_id: str) -> bool:
        data = self._request_json("DELETE", "/memory", {"memory_id": memory_id})
        return bool(data.get("deleted", False))

    def clear_memory(self) -> int:
        data = self._request_json("DELETE", "/memory", {"all": True})
        return int(data.get("deleted_count", 0))

    def transcribe_wav(self, path: Path) -> str:
        payload = {
            "filename": path.name,
            "wav_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
        data = self._request_json("POST", "/transcribe", payload)
        return str(data.get("text") or "").strip()

    # --- Raw helpers used by the desktop app's Python<->JS bridge -------------
    def metadata_dict(self) -> Dict[str, Any]:
        """Full /metadata payload (app fields + boot_lines + has_avatars)."""
        return self._request_json("GET", "/metadata", tolerate_errors=True) or {}

    def chat_payload(self, text: str) -> Dict[str, Any]:
        """Raw /chat response, including audio_wav_base64 for in-UI playback."""
        return self._request_json("POST", "/chat", {"text": text})

    def fetch_avatars(self) -> Dict[str, Any]:
        """Emotion -> {idle[, talking]} base64 PNG map from /assets/avatars.

        Returns an empty dict if the backend serves no avatars.
        """
        return self._request_json("GET", "/assets/avatars", tolerate_errors=True) or {}

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        tolerate_errors: bool = False,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "MiguelLM/%s" % __version__,
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.token:
            headers["Authorization"] = "Bearer %s" % self.token
        request = urllib.request.Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds or self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            if tolerate_errors:
                return {}
            raise RemoteServiceError("Remote service HTTP %s: %s" % (exc.code, details)) from exc
        except Exception as exc:
            if tolerate_errors:
                return {}
            raise RemoteServiceError("Remote service is not reachable at %s: %s" % (self.url, exc)) from exc


class _RemotePushToTalk(PushToTalkInput):
    def __init__(self, recorder: FfmpegAudioRecorder, remote: RemoteClientRuntime) -> None:
        super().__init__(recorder, stt_provider=None)
        self.remote = remote

    async def listen_once(self) -> str:
        if self._tempdir is None:
            raise RuntimeError("Push-to-talk input must be used as an async context manager.")
        output_path = Path(self._tempdir.name) / "visitor.wav"
        recorded = await self.recorder.record_once(output_path)
        if recorded.rms < 120:
            raise RuntimeError("Recording was very quiet. Check the selected microphone/device.")
        return await _run_blocking(self.remote.transcribe_wav, recorded.path)


def _clip_from_response_audio(data: Dict[str, Any], text: str) -> Optional[AudioClip]:
    encoded = data.get("audio_wav_base64")
    if not encoded:
        return None
    sample_rate = int(data.get("sample_rate") or 24000)
    wav_bytes = base64.b64decode(str(encoded).encode("ascii"))
    pcm = wav_bytes_to_pcm16_mono(wav_bytes, sample_rate)
    return AudioClip(pcm=pcm, sample_rate=sample_rate, text=text, provider=str(data.get("audio_provider") or "remote"))


async def _run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return await loop.run_in_executor(executor, partial(func, *args))
