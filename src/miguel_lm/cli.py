from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from miguel_lm.audio_codec import pcm16_mono_to_wav_bytes
from miguel_lm.audio_input import FfmpegAudioRecorder, list_ffmpeg_audio_devices, scan_audio_inputs
from miguel_lm.config import AppConfig, write_user_env
from miguel_lm.remote import RemoteClientRuntime


DEFAULT_CLIENT_CONFIG = "package:client.yaml"


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="miguellm")
    parser.set_defaults(func=run_command)
    add_config_arg(parser)
    parser.add_argument("--text-only", action="store_true", help="Disable push-to-talk input in the TUI.")

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run the terminal client.")
    add_config_arg(run)
    run.add_argument("--text-only", action="store_true", help="Disable push-to-talk input in the TUI.")
    run.set_defaults(func=run_command)

    configure = sub.add_parser("configure", help="Save your MiguelLM token for use from any directory.")
    configure.add_argument("--token", required=True, help="MiguelLM backend token.")
    configure.add_argument("--backend-url", default="", help="Optional backend URL override.")
    configure.set_defaults(func=configure_command)

    test_tts = sub.add_parser("test-voice", help="Synthesize speech through the configured remote service.")
    add_config_arg(test_tts)
    test_tts.add_argument("--text", default="Voice test from the terminal client.")
    test_tts.add_argument("--output", default="tmp/voice-test.wav", help="Where to save the synthesized WAV.")
    test_tts.add_argument("--no-play", action="store_true", help="Save the WAV without playing it locally.")
    test_tts.set_defaults(func=test_voice_command)

    audio_devices = sub.add_parser("audio-devices", help="List ffmpeg/avfoundation audio input devices.")
    add_config_arg(audio_devices)
    audio_devices.set_defaults(func=audio_devices_command)

    scan_audio = sub.add_parser("scan-audio-inputs", help="Record from each audio device and rank by signal level.")
    add_config_arg(scan_audio)
    scan_audio.add_argument("--seconds", type=float, default=1.5, help="Seconds to record per device.")
    scan_audio.add_argument("--output-dir", default="tmp/audio-scan", help="Directory for scan WAV files.")
    scan_audio.set_defaults(func=scan_audio_inputs_command)

    test_audio = sub.add_parser("test-audio-input", help="Record a short microphone clip and optionally transcribe it.")
    add_config_arg(test_audio)
    test_audio.add_argument("--seconds", type=float, default=None, help="Recording duration.")
    test_audio.add_argument("--audio-device", default=None, help='Override ffmpeg input device, for example "none:1".')
    test_audio.add_argument("--output", default="tmp/visitor-test.wav", help="Where to save the test WAV.")
    test_audio.add_argument("--transcribe", action="store_true", help="Also run remote transcription.")
    test_audio.set_defaults(func=test_audio_input_command)

    memory = sub.add_parser("memory", help="Manage remote memories outside the TUI.")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_list = memory_sub.add_parser("list", help="List active memories.")
    add_config_arg(memory_list)
    memory_list.set_defaults(func=memory_list_command)
    memory_clear = memory_sub.add_parser("clear", help="Delete all memories.")
    add_config_arg(memory_clear)
    memory_clear.set_defaults(func=memory_clear_command)
    memory_delete = memory_sub.add_parser("delete", help="Delete one memory by id.")
    add_config_arg(memory_delete)
    memory_delete.add_argument("memory_id")
    memory_delete.set_defaults(func=memory_delete_command)

    return parser


def add_config_arg(parser: argparse.ArgumentParser, default: str = DEFAULT_CLIENT_CONFIG) -> None:
    parser.add_argument("--config", default=default, help="Path to YAML config.")


def build_runtime(config: AppConfig) -> RemoteClientRuntime:
    if config.backend.mode != "remote":
        raise RuntimeError("This public package only supports remote client mode.")
    return RemoteClientRuntime(config)


def configure_command(args) -> int:
    path = write_user_env(args.token, backend_url=args.backend_url)
    print("Saved MiguelLM configuration to %s" % path)
    print("You can now run: python -m miguellm")
    return 0


def run_command(args) -> int:
    from miguel_lm.tui import TerminalClientApp

    config = AppConfig.load(args.config)
    runtime = build_runtime(config)
    TerminalClientApp(runtime, text_only=getattr(args, "text_only", False)).run()
    return 0


def audio_devices_command(args) -> int:
    config = AppConfig.load(args.config)
    print(asyncio.run(list_ffmpeg_audio_devices(config.input_audio.ffmpeg_bin)))
    return 0


def scan_audio_inputs_command(args) -> int:
    config = AppConfig.load(args.config)
    results = asyncio.run(scan_audio_inputs(config.input_audio, seconds=args.seconds, output_dir=Path(args.output_dir)))
    if not results:
        print("No ffmpeg/avfoundation audio devices found.")
        return 1
    print("Audio input scan ranked by RMS:")
    for result in results:
        if result.ok:
            print(
                "%s %-28s RMS=%7.1f size=%s file=%s"
                % (result.input_name, result.device.name, result.rms, result.size_bytes, result.path)
            )
        else:
            print("%s %-28s ERROR=%s" % (result.input_name, result.device.name, result.error))
    best = results[0]
    if best.ok:
        print("Best candidate: %s (%s)" % (best.input_name, best.device.name))
    return 0


def test_audio_input_command(args) -> int:
    config = AppConfig.load(args.config)
    if args.seconds is not None:
        config.input_audio.record_seconds = args.seconds
    if args.audio_device:
        config.input_audio.device = args.audio_device
    asyncio.run(_test_audio_input(config, Path(args.output), transcribe=args.transcribe))
    return 0


async def _test_audio_input(config: AppConfig, output_path: Path, transcribe: bool) -> None:
    recorder = FfmpegAudioRecorder(config.input_audio)
    print("Recording device %s for %.1f seconds..." % (config.input_audio.device, config.input_audio.record_seconds))
    recorded = await recorder.record_once(output_path)
    print("Saved: %s" % recorded.path)
    print("Size: %s bytes" % recorded.size_bytes)
    print("RMS: %.1f" % recorded.rms)
    if recorded.rms < 120:
        print("Warning: recording is very quiet. Try a different --audio-device or speak closer/louder.")
    if transcribe:
        print("Transcribing remotely...")
        text = RemoteClientRuntime(config).transcribe_wav(recorded.path)
        print("Transcript: %s" % (text or "<empty>"))


def test_voice_command(args) -> int:
    config = AppConfig.load(args.config)
    asyncio.run(_test_voice(config, text=args.text, output_path=Path(args.output), play=not args.no_play))
    return 0


async def _test_voice(config: AppConfig, text: str, output_path: Path, play: bool) -> None:
    runtime = RemoteClientRuntime(config)
    print("Voice provider: remote")
    print("Endpoint: %s" % runtime.url)
    clip = await runtime.synthesize(text)
    resolved_output = config.resolve(str(output_path))
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_bytes(pcm16_mono_to_wav_bytes(clip.pcm, clip.sample_rate))
    print("Saved WAV: %s" % resolved_output)
    print("Audio: %d bytes PCM at %d Hz" % (len(clip.pcm), clip.sample_rate))
    if play:
        print("Playing locally...")
        await runtime.player.play(clip)


def memory_list_command(args) -> int:
    runtime = build_runtime(AppConfig.load(args.config))
    rows = runtime.memory_summary()
    print("\n".join(rows) if rows else "No memories stored.")
    return 0


def memory_clear_command(args) -> int:
    runtime = build_runtime(AppConfig.load(args.config))
    print("Deleted %d memories." % runtime.clear_memory())
    return 0


def memory_delete_command(args) -> int:
    runtime = build_runtime(AppConfig.load(args.config))
    if runtime.delete_memory(args.memory_id):
        print("Deleted %s." % args.memory_id)
        return 0
    print("No memory with id %s." % args.memory_id)
    return 1
