from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from miguel_lm.audio_codec import pcm16_mono_to_wav_bytes
from miguel_lm.config import PlaybackSettings
from miguel_lm.models import AudioClip


class PlaybackError(RuntimeError):
    pass


class AudioPlayer:
    def __init__(self, settings: PlaybackSettings, tmp_dir: Path) -> None:
        self.settings = settings
        self.tmp_dir = tmp_dir

    def available_player(self) -> Optional[str]:
        if self.settings.player != "auto":
            return self.settings.player if shutil.which(self.settings.player) else None
        for candidate in ["afplay", "ffplay", "aplay"]:
            if shutil.which(candidate):
                return candidate
        return None

    async def play(self, clip: AudioClip) -> Path:
        player = self.available_player()
        if not player:
            raise PlaybackError("No local audio player found. Install afplay, ffplay, or aplay.")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        wav_bytes = pcm16_mono_to_wav_bytes(clip.pcm, clip.sample_rate)
        with NamedTemporaryFile(prefix="miguellm-", suffix=".wav", dir=str(self.tmp_dir), delete=False) as handle:
            handle.write(wav_bytes)
            path = Path(handle.name)
        try:
            await asyncio.to_thread(self._play_blocking, player, path)
        finally:
            if not self.settings.keep_wavs:
                path.unlink(missing_ok=True)
        return path

    def _play_blocking(self, player: str, path: Path) -> None:
        if player == "ffplay":
            command = [player, "-nodisp", "-autoexit", "-loglevel", "error", str(path)]
        else:
            command = [player, str(path)]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            raise PlaybackError((completed.stderr or completed.stdout or "audio playback failed").strip())
