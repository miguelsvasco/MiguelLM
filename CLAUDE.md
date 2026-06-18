# CLAUDE.md

Guidance for working in this repository.

## What This Is

MiguelLM is a standalone terminal app for talking to Miguel's synthetic clone.
It does not require Furhat, Virtual Furhat, face recognition, robot animation,
or robot audio. The public client talks to a private Linux backend so OpenAI
secrets and local F5-TTS paths stay off GitHub and off visitor machines.

The user-facing app name is **MiguelLM** and the command is:

```bash
miguellm
```

Python 3.9+ is supported.

## Layout

- `src/miguel_lm/cli.py` — argparse CLI. No subcommand launches the TUI directly.
- `src/miguel_lm/tui.py` — Textual/Rich green CRT terminal UI.
- `src/miguel_lm/engine.py` — local/private runtime wiring for persona, memory, dialogue, STT, TTS, and playback.
- `src/miguel_lm/remote.py` — public client runtime that calls the private backend.
- `src/miguel_lm/server.py` — private Linux HTTP backend used by `miguellm serve`.
- `src/miguel_lm/tts_supervisor.py` — optional local F5-TTS autostart from Linux-only env vars.
- `src/miguel_lm/providers/` — dialogue, STT, and local HTTP TTS providers.
- `src/miguel_lm/memory.py` — local opt-in memories and transcript storage.
- `src/miguel_lm/persona.py` plus `persona/*.md` — public-safe placeholder persona pack.
- `config/dev.yaml` — default local development config.

## Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

miguellm
miguellm serve --config config/server.yaml --host 127.0.0.1 --port 8765
miguellm validate-persona --config config/dev.yaml
miguellm test-tts --config config/dev.yaml
miguellm test-audio-input --config config/dev.yaml --transcribe
python -m pytest -q
```

## Boundaries

- Keep this repo self-contained. Do not import from `../miguel_furhat_llm`.
- Do not add Furhat realtime clients, face recognition, presence detection, or robot animation to v1.
- Public `config/dev.yaml` must not require `OPENAI_API_KEY`; keep it in remote backend mode.
- `config/server.yaml` may reference secret env var names, but never commit actual tokens, API keys, Linux paths with credentials, or private voice artifacts.
- Do not recommend publishing a raw Linux server IP. Run `miguellm serve` on localhost and expose it with Cloudflare Tunnel or Tailscale Funnel.
- Keep the checked-in `persona/` public-safe. The real Miguel persona belongs outside Git and is loaded on Linux via `MIGUELLM_PERSONA_DIR`.
- Local F5-TTS is the backend voice path. If it is offline, the app should keep working as text-only.
- OpenAI dialogue/STT run only on the private backend by default; transcripts, memories, consent state, and private voice assets stay local and git-ignored.
- Durable memories are opt-in. Do not bypass `PrivacyConsentStore`.
- The terminal app should stay readable and retro-looking, but UI polish must not make the core chat loop brittle.
