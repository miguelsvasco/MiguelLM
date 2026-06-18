from miguel_lm.cli import build_parser, configure_command
from miguel_lm.config import AppConfig, user_env_path


def test_miguellm_without_subcommand_runs_default():
    parser = build_parser()
    args = parser.parse_args([])

    assert args.config == "package:client.yaml"
    assert args.command is None
    assert callable(args.func)


def test_miguellm_run_subcommand_accepts_text_only():
    parser = build_parser()
    args = parser.parse_args(["run", "--text-only"])

    assert args.command == "run"
    assert args.text_only is True


def test_public_cli_does_not_expose_server_or_persona_commands():
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices

    assert "serve" not in choices
    assert "validate-persona" not in choices
    assert "configure" in choices


def test_packaged_client_config_loads_without_persona(monkeypatch):
    monkeypatch.setenv("MIGUELLM_BACKEND_URL", "")

    config = AppConfig.load("package:client.yaml")

    assert config.app_name == "MiguelLM"
    assert config.backend.mode == "remote"
    assert config.backend.resolved_url == "https://miguellm.miguelvasco.com"


def test_user_config_env_file_is_loaded(monkeypatch, tmp_path):
    config_home = tmp_path / "xdg"
    env_path = config_home / "miguellm" / ".env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("MIGUELLM_BACKEND_TOKEN=from-user-config\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("MIGUELLM_BACKEND_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)

    config = AppConfig.load("package:client.yaml")

    assert config.backend.client_token == "from-user-config"


def test_configure_command_writes_user_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    args = build_parser().parse_args(["configure", "--token", "configured-token"])

    assert configure_command(args) == 0
    assert user_env_path().read_text(encoding="utf-8") == "MIGUELLM_BACKEND_TOKEN=configured-token\n"
