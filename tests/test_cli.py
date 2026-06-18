from miguel_lm.cli import build_parser
from miguel_lm.config import AppConfig


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


def test_packaged_client_config_loads_without_persona(monkeypatch):
    monkeypatch.setenv("MIGUELLM_BACKEND_URL", "")

    config = AppConfig.load("package:client.yaml")

    assert config.app_name == "MiguelLM"
    assert config.backend.mode == "remote"
    assert config.backend.resolved_url == "https://miguellm.miguelvasco.com"
