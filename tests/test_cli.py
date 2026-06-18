from miguel_lm.cli import build_parser


def test_miguellm_without_subcommand_runs_default():
    parser = build_parser()
    args = parser.parse_args([])

    assert args.config == "config/dev.yaml"
    assert args.command is None
    assert callable(args.func)


def test_miguellm_run_subcommand_accepts_text_only():
    parser = build_parser()
    args = parser.parse_args(["run", "--text-only"])

    assert args.command == "run"
    assert args.text_only is True


def test_miguellm_serve_defaults_to_server_config():
    parser = build_parser()
    args = parser.parse_args(["serve"])

    assert args.command == "serve"
    assert args.config == "config/server.yaml"
    assert args.port == 8765
