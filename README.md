# MiguelLM

MiguelLM is a small terminal client for a hosted chat service. Install it,
point it at the service URL you were given, and run `miguellm`.

The public package is client-only. It does not include server code, persona
files, private prompts, model provider setup, voice assets, or operator notes.
Display copy such as the app title, intro text, assistant label, and voice test
line can be provided by the remote service at runtime.

## Install

```bash
python -m pip install miguellm
```

Until the first PyPI release is published, install directly from GitHub:

```bash
python -m pip install git+https://github.com/miguelsvasco/MiguelLM.git
```

`pipx` also works well if you want an isolated command-line install:

```bash
pipx install git+https://github.com/miguelsvasco/MiguelLM.git
```

## Configure

The default backend is `https://miguellm.miguelvasco.com`. Create a local
`.env` or `.env.local` file in the directory where you will run the command:

```dotenv
MIGUELLM_BACKEND_TOKEN=your-token
```

For development or alternate deployments, you can override the default with
`MIGUELLM_BACKEND_URL`. Do not put private server files, prompts, model keys, or
voice assets in this client checkout.

## Run

```bash
miguellm
```

Inside the app, type a message and press Enter. Use `/help` for available
commands.

Useful checks:

```bash
miguellm run --text-only
miguellm test-voice --no-play
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/check_public_safety.py
```

Build the package locally:

```bash
python -m build
twine check dist/*
```

## Privacy

This client sends chat text, optional microphone recordings, and memory commands
to the configured remote service. Server behavior, prompts, and storage policy
are controlled by that service, not by this public client package.

## Credits

MiguelLM is by Miguel Vasco.

## License

MIT
