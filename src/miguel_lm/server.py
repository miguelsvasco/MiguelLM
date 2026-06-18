from __future__ import annotations

import argparse
import asyncio
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional, Tuple

from miguel_lm.audio_codec import pcm16_mono_to_wav_bytes
from miguel_lm.config import AppConfig
from miguel_lm.engine import MiguelLMRuntime
from miguel_lm.models import DialogueResponse
from miguel_lm.providers.local_http_tts_provider import LocalHttpTTSProvider
from miguel_lm.tts_supervisor import TTSSupervisor


class BackendService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.runtime = MiguelLMRuntime.build(config)
        self.tts_start_status = TTSSupervisor(config, self.runtime.tts_provider).ensure_running()

    def health(self) -> Dict[str, Any]:
        status = self.runtime.status()
        return {
            "ok": True,
            "app": self.config.app_name,
            "tts_provider": status.tts_provider,
            "tts_healthy": status.tts_healthy,
            "tts_start_status": self.tts_start_status,
            "memory_enabled": status.memory_enabled,
        }

    async def chat(self, text: str) -> Dict[str, Any]:
        response = await self.runtime.answer(text)
        payload = {
            "response": response.to_dict(),
            "provider": response.provider,
        }
        payload.update(await self._audio_payload(response.spoken_text))
        return payload

    async def synthesize(self, text: str) -> Dict[str, Any]:
        return await self._audio_payload(text)

    async def transcribe(self, wav_base64: str, filename: str = "visitor.wav") -> Dict[str, Any]:
        if self.runtime.stt_provider is None:
            raise RuntimeError("No STT provider configured on the MiguelLM backend.")
        suffix = Path(filename).suffix or ".wav"
        with NamedTemporaryFile(prefix="miguellm-upload-", suffix=suffix, delete=False) as handle:
            path = Path(handle.name)
            handle.write(base64.b64decode(wav_base64.encode("ascii")))
        try:
            text = await self.runtime.stt_provider.transcribe_file(str(path))
            return {"text": text}
        finally:
            path.unlink(missing_ok=True)

    def memory_get(self) -> Dict[str, Any]:
        return {
            "memory_enabled": self.runtime.memory_store.memory_allowed(),
            "memories": [record.to_dict() for record in self.runtime.memory_store.list_records()],
        }

    def memory_post(self, enabled: bool) -> Dict[str, Any]:
        return {"memory_enabled": self.runtime.set_memory_enabled(enabled)}

    def memory_delete(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if payload.get("all"):
            return {"deleted_count": self.runtime.clear_memory()}
        memory_id = str(payload.get("memory_id") or "")
        return {"deleted": self.runtime.delete_memory(memory_id)}

    async def _audio_payload(self, text: str) -> Dict[str, Any]:
        try:
            clip = await self.runtime.synthesize(text)
        except Exception as exc:
            return {"audio_error": str(exc)}
        if clip is None:
            return {"audio_error": "No TTS provider configured."}
        wav = pcm16_mono_to_wav_bytes(clip.pcm, clip.sample_rate)
        return {
            "audio_wav_base64": base64.b64encode(wav).decode("ascii"),
            "sample_rate": clip.sample_rate,
            "audio_provider": clip.provider,
        }


class MiguelLMHandler(BaseHTTPRequestHandler):
    service: BackendService

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(self.service.health())
            return
        if self.path == "/memory":
            if not self._authorized():
                return
            self._send_json(self.service.memory_get())
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path not in {"/chat", "/synthesize", "/transcribe", "/memory"}:
            self._send_json({"error": "not found"}, status=404)
            return
        if not self._authorized():
            return
        try:
            payload = self._read_json()
            if self.path == "/chat":
                result = asyncio.run(self.service.chat(str(payload.get("text") or "")))
            elif self.path == "/synthesize":
                result = asyncio.run(self.service.synthesize(str(payload.get("text") or "")))
            elif self.path == "/transcribe":
                result = asyncio.run(
                    self.service.transcribe(
                        str(payload.get("wav_base64") or ""),
                        filename=str(payload.get("filename") or "visitor.wav"),
                    )
                )
            else:
                result = self.service.memory_post(bool(payload.get("enabled", False)))
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_DELETE(self) -> None:
        if self.path != "/memory":
            self._send_json({"error": "not found"}, status=404)
            return
        if not self._authorized():
            return
        try:
            self._send_json(self.service.memory_delete(self._read_json()))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _authorized(self) -> bool:
        token = self.service.config.backend.server_token
        if not token:
            return True
        header = self.headers.get("Authorization") or ""
        supplied = self.headers.get("X-MiguelLM-Token") or ""
        if header.startswith("Bearer "):
            supplied = header[len("Bearer ") :].strip()
        if supplied == token:
            return True
        self._send_json({"error": "unauthorized"}, status=401)
        return False

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(config: AppConfig, host: str, port: int) -> None:
    service = BackendService(config)
    MiguelLMHandler.service = service
    server = ThreadingHTTPServer((host, port), MiguelLMHandler)
    print("MiguelLM backend listening on http://%s:%d" % (host, port))
    print("TTS startup status: %s" % service.tts_start_status)
    server.serve_forever()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="miguellm-serve")
    parser.add_argument("--config", default="config/server.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    serve(AppConfig.load(args.config), args.host, args.port)
    return 0
