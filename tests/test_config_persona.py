from pathlib import Path

from miguel_lm.config import AppConfig
from miguel_lm.persona import PersonaPack


def test_config_loads_miguellm_defaults():
    config = AppConfig.load("config/dev.yaml")

    assert config.app_name == "MiguelLM"
    assert config.backend.mode == "remote"
    assert config.backend.resolved_url == "http://127.0.0.1:8765"
    assert config.paths.persona_dir == "persona"


def test_server_config_uses_local_private_backend():
    config = AppConfig.load("config/server.yaml")

    assert config.backend.mode == "local"
    assert config.voice.provider == "local_http"
    assert config.tts_server.autostart is True


def test_persona_pack_validates_required_files():
    pack = PersonaPack.load(Path("persona"))

    names = {doc.name for doc in pack.documents}
    assert "identity.md" in names
    assert "boundaries.md" in names
    assert "MiguelLM" in pack.render_system_prompt()
