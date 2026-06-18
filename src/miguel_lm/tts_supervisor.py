from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional

from miguel_lm.config import AppConfig
from miguel_lm.providers.local_http_tts_provider import LocalHttpTTSProvider


class TTSSupervisor:
    def __init__(self, config: AppConfig, provider: Optional[object]) -> None:
        self.config = config
        self.provider = provider
        self.process: Optional[subprocess.Popen] = None

    def ensure_running(self) -> str:
        if not isinstance(self.provider, LocalHttpTTSProvider):
            return "not-local-http"
        if self.provider.healthy(timeout=2.0):
            return "already-running"
        if not self.config.tts_server.autostart:
            return "offline-autostart-disabled"
        command = os.environ.get(self.config.tts_server.command_env, "").strip()
        if not command:
            return "offline-no-start-command"
        cwd_value = os.environ.get(self.config.tts_server.cwd_env, "").strip()
        cwd = Path(cwd_value).expanduser() if cwd_value else self.config.root
        log_path = self.config.resolve(self.config.tts_server.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("ab")
        self.process = subprocess.Popen(
            shlex.split(command),
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + self.config.tts_server.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.provider.healthy(timeout=2.0):
                return "started"
            if self.process.poll() is not None:
                return "start-command-exited"
            time.sleep(1.0)
        return "start-timeout"
