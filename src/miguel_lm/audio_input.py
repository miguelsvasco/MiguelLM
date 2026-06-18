from __future__ import annotations

import asyncio
import math
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional

from miguel_lm.config import InputAudioSettings


class AudioInputError(RuntimeError):
    pass


@dataclass
class RecordedAudio:
    path: Path
    seconds: float
    recorder: str
    size_bytes: int
    rms: float


@dataclass
class AudioDevice:
    index: int
    name: str


@dataclass
class AudioDeviceScanResult:
    device: AudioDevice
    input_name: str
    ok: bool
    rms: float = 0.0
    size_bytes: int = 0
    path: Optional[Path] = None
    error: str = ""


class FfmpegAudioRecorder:
    def __init__(self, settings: InputAudioSettings) -> None:
        self.settings = settings

    def command(self, output_path: Path, seconds: Optional[float] = None) -> List[str]:
        duration = seconds if seconds is not None else self.settings.record_seconds
        if self.settings.recorder == "ffmpeg_avfoundation":
            return [
                self.settings.ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                self.settings.device,
                "-t",
                "%.3f" % float(duration),
                "-ac",
                str(self.settings.channels),
                "-ar",
                str(self.settings.sample_rate),
                str(output_path),
            ]
        return [
            self.settings.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            self.settings.device,
            "-t",
            "%.3f" % float(duration),
            "-ac",
            str(self.settings.channels),
            "-ar",
            str(self.settings.sample_rate),
            str(output_path),
        ]

    async def record_once(self, output_path: Path, seconds: Optional[float] = None) -> RecordedAudio:
        if not shutil.which(self.settings.ffmpeg_bin):
            raise AudioInputError("ffmpeg is not available on PATH.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        completed = await asyncio.to_thread(
            subprocess.run,
            self.command(output_path, seconds=seconds),
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise AudioInputError((completed.stderr or completed.stdout or "ffmpeg recording failed").strip())
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise AudioInputError("Recording produced an empty audio file: %s" % output_path)
        return RecordedAudio(
            output_path,
            seconds or self.settings.record_seconds,
            self.settings.recorder,
            output_path.stat().st_size,
            wav_rms(output_path),
        )


async def list_ffmpeg_audio_devices(ffmpeg_bin: str = "ffmpeg") -> str:
    if not shutil.which(ffmpeg_bin):
        raise AudioInputError("ffmpeg is not available on PATH.")
    completed = await asyncio.to_thread(
        subprocess.run,
        [ffmpeg_bin, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    return output.strip()


async def scan_audio_inputs(settings: InputAudioSettings, seconds: float = 1.5, output_dir: Optional[Path] = None) -> List[AudioDeviceScanResult]:
    output = await list_ffmpeg_audio_devices(settings.ffmpeg_bin)
    devices = parse_avfoundation_audio_devices(output)
    output_dir = output_dir or Path("tmp/audio-scan")
    results: List[AudioDeviceScanResult] = []
    for device in devices:
        device_settings = InputAudioSettings(
            recorder=settings.recorder,
            ffmpeg_bin=settings.ffmpeg_bin,
            device="none:%d" % device.index,
            record_seconds=seconds,
            sample_rate=settings.sample_rate,
            channels=settings.channels,
            transcribe=settings.transcribe,
        )
        recorder = FfmpegAudioRecorder(device_settings)
        path = output_dir / ("device-%d.wav" % device.index)
        try:
            recorded = await recorder.record_once(path, seconds=seconds)
            results.append(
                AudioDeviceScanResult(
                    device=device,
                    input_name=device_settings.device,
                    ok=True,
                    rms=recorded.rms,
                    size_bytes=recorded.size_bytes,
                    path=recorded.path,
                )
            )
        except Exception as exc:
            results.append(AudioDeviceScanResult(device=device, input_name=device_settings.device, ok=False, error=str(exc)))
    results.sort(key=lambda item: item.rms, reverse=True)
    return results


def parse_avfoundation_audio_devices(output: str) -> List[AudioDevice]:
    devices = []
    in_audio_section = False
    pattern = re.compile(r"\[(\d+)\]\s+(.+)$")
    for line in output.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio_section = True
            continue
        if "AVFoundation video devices:" in line:
            in_audio_section = False
            continue
        if not in_audio_section:
            continue
        match = pattern.search(line)
        if match:
            devices.append(AudioDevice(index=int(match.group(1)), name=match.group(2).strip()))
    return devices


class PushToTalkInput:
    def __init__(self, recorder: FfmpegAudioRecorder, stt_provider) -> None:
        self.recorder = recorder
        self.stt_provider = stt_provider
        self._tempdir: Optional[TemporaryDirectory] = None

    async def __aenter__(self) -> "PushToTalkInput":
        self._tempdir = TemporaryDirectory(prefix="miguellm-audio-")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._tempdir:
            self._tempdir.cleanup()
            self._tempdir = None

    async def listen_once(self) -> str:
        if self._tempdir is None:
            raise AudioInputError("PushToTalkInput must be used as an async context manager.")
        output_path = Path(self._tempdir.name) / "visitor.wav"
        recorded = await self.recorder.record_once(output_path)
        if recorded.rms < 120:
            raise AudioInputError("Recording was very quiet. Check the selected microphone/device.")
        text = (await self.stt_provider.transcribe_file(str(recorded.path))).strip()
        if not text:
            raise AudioInputError("Transcription was empty.")
        return text


def wav_rms(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        width = handle.getsampwidth()
        channels = handle.getnchannels()
        frames = handle.readframes(handle.getnframes())
    if width != 2 or not frames:
        return 0.0
    total = 0
    count = 0
    step = width * channels
    for offset in range(0, len(frames) - step + 1, step):
        sample = int.from_bytes(frames[offset : offset + 2], byteorder="little", signed=True)
        total += sample * sample
        count += 1
    if count == 0:
        return 0.0
    return math.sqrt(total / count)
