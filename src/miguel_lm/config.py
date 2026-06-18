from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ConfigError(RuntimeError):
    pass


YamlSource = Union[Path, Any]


def _load_yaml(path: YamlSource) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required. Install with: python -m pip install -e '.[dev]'") from exc
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError("Config root must be a mapping: %s" % path)
    return data


def _project_root_for(config_path: Path) -> Path:
    config_path = config_path.resolve()
    if config_path.parent.name == "config":
        return config_path.parent.parent
    return config_path.parent


def load_local_secrets(root: Path) -> List[Path]:
    loaded = []
    for name in [".env", ".env.local"]:
        path = root / name
        if path.exists():
            _load_env_file(path)
            loaded.append(path)
    return loaded


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_inline_comment(value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _strip_inline_comment(value: str) -> str:
    quote = None
    for index, char in enumerate(value):
        if char in {"'", '"'}:
            quote = char if quote is None else None if quote == char else quote
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value


@dataclass
class InputAudioSettings:
    recorder: str = "ffmpeg_avfoundation"
    ffmpeg_bin: str = "ffmpeg"
    device: str = "none:0"
    record_seconds: float = 5.0
    sample_rate: int = 16000
    channels: int = 1
    transcribe: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybackSettings:
    player: str = "auto"
    keep_wavs: bool = False


@dataclass
class BackendSettings:
    mode: str = "remote"
    url: str = "http://127.0.0.1:8765"
    url_env: str = "MIGUELLM_BACKEND_URL"
    token_env: str = "MIGUELLM_BACKEND_TOKEN"
    timeout_seconds: float = 120.0

    @property
    def resolved_url(self) -> str:
        return os.environ.get(self.url_env) or self.url

    @property
    def client_token(self) -> str:
        return os.environ.get(self.token_env) or ""


@dataclass
class PathsSettings:
    sessions_dir: str = "sessions"
    tmp_dir: str = "tmp"


@dataclass
class AppConfig:
    root: Path
    app: Dict[str, Any]
    input_audio: InputAudioSettings
    playback: PlaybackSettings
    backend: BackendSettings
    paths: PathsSettings

    @classmethod
    def load(cls, path: str) -> "AppConfig":
        if path.startswith("package:"):
            return cls.load_default(path.removeprefix("package:"))
        config_path = Path(path)
        data = _load_yaml(config_path)
        root = _project_root_for(config_path)
        load_local_secrets(root)
        if root != Path.cwd():
            load_local_secrets(Path.cwd())
        return cls.from_dict(root, data)

    @classmethod
    def load_default(cls, name: str) -> "AppConfig":
        if name != "client.yaml":
            raise ConfigError("Unknown bundled config: %s" % name)
        defaults = resources.files("miguel_lm").joinpath("defaults")
        data = _load_yaml(defaults.joinpath(name))
        load_local_secrets(Path.cwd())
        return cls.from_dict(Path.cwd(), data)

    @classmethod
    def from_dict(cls, root: Path, data: Dict[str, Any]) -> "AppConfig":
        return cls(
            root=root,
            app=dict(data.get("app") or {}),
            input_audio=InputAudioSettings(**dict(data.get("input_audio") or {})),
            playback=PlaybackSettings(**dict(data.get("playback") or {})),
            backend=BackendSettings(**dict(data.get("backend") or {})),
            paths=PathsSettings(**dict(data.get("paths") or {})),
        )

    def resolve(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return (self.root / candidate).resolve()

    @property
    def app_name(self) -> str:
        return str(self.app.get("name") or "MiguelLM")

    @property
    def intro_text(self) -> str:
        return str(self.app.get("intro_text") or "").strip()
