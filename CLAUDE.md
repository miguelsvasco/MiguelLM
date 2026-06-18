# CLAUDE.md

Guidance for working in this repository, especially on the Linux server.

## Current Goal

MiguelLM is a standalone terminal app for talking to Miguel's synthetic clone.
The public client must not need OpenAI secrets, private persona files, private
voice assets, or a raw server IP. The intended architecture is:

```text
public laptop/client
  -> miguellm TUI
  -> Cloudflare Tunnel HTTPS hostname
  -> miguellm serve on Linux at 127.0.0.1:8765
  -> OpenAI dialogue/STT + local F5-TTS
```

If the user starts Codex on Linux to "fix MiguelLM", first inspect this file,
`.env.local`, `config/server.yaml`, and the sibling `miguel_furhat_llm` checkout.

## Expected Linux Paths

The observed Linux checkout path from the recent error was:

```text
/home/miguelsv/miguel/code/MiguelLM
```

Likely sibling Furhat/TTS repo path:

```text
/home/miguelsv/miguel/code/miguel_furhat_llm
```

Do not assume `/home/miguel/...`; verify with `pwd`, `ls`, and `.env.local`.

The private persona directory should exist outside Git, usually:

```text
/home/miguelsv/private/miguellm-persona
```

If `miguellm serve` fails with:

```text
PersonaValidationError: Persona directory does not exist
```

then either create the private persona folder or fix `MIGUELLM_PERSONA_DIR` in
`.env.local`:

```bash
cd /home/miguelsv/miguel/code/MiguelLM
mkdir -p /home/miguelsv/private/miguellm-persona
cp persona/*.md /home/miguelsv/private/miguellm-persona/
```

Then set:

```dotenv
MIGUELLM_PERSONA_DIR=/home/miguelsv/private/miguellm-persona
```

The checked-in `persona/` folder is intentionally public-safe placeholder
content. The real Miguel persona belongs outside Git.

## Commands

Setup:

```bash
cd /home/miguelsv/miguel/code/MiguelLM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Validate:

```bash
source .venv/bin/activate
miguellm validate-persona --config config/server.yaml
python -m pytest -q
```

Run private backend locally:

```bash
miguellm serve --config config/server.yaml --host 127.0.0.1 --port 8765
```

Check backend health:

```bash
curl http://127.0.0.1:8765/health
```

Do not bind to `0.0.0.0` unless the user explicitly accepts LAN exposure.
Preferred public exposure is Cloudflare Tunnel pointing at
`http://127.0.0.1:8765`.

## Private `.env.local`

The Linux server should keep secrets and private paths in `.env.local`, never in
Git. Expected shape:

```dotenv
OPENAI_API_KEY=...
OPENAI_DIALOGUE_MODEL=gpt-5.4-mini
OPENAI_TRANSCRIBE_MODEL=whisper-1
LOCAL_TTS_ENDPOINT=http://127.0.0.1:7861/synthesize

MIGUELLM_BACKEND_TOKEN=...
MIGUELLM_PERSONA_DIR=/home/miguelsv/private/miguellm-persona

MIGUELLM_TTS_CWD=/home/miguelsv/miguel/code/miguel_furhat_llm
MIGUELLM_TTS_START_COMMAND=bash -lc 'source .venv-f5/bin/activate && python scripts/f5_tts_server.py --host 127.0.0.1 --port 7861 --device cuda --nfe-step 16 --speed 1.08 --ref-audio assets/input/audio/f5_reference.wav --ref-text-file assets/input/audio/f5_reference.txt'
```

Do not print actual secret values in final answers. It is okay to mention env var
names.

## Relationship To `miguel_furhat_llm`

MiguelLM is self-contained and must not import from `../miguel_furhat_llm`.
However, the Linux backend can use the existing Furhat repo as the F5-TTS host:

- `miguel_furhat_llm/scripts/f5_tts_server.py` is the F5-TTS HTTP server.
- It serves `POST /synthesize` and returns WAV audio.
- MiguelLM talks to it through `LOCAL_TTS_ENDPOINT`, usually
  `http://127.0.0.1:7861/synthesize`.
- `miguel_furhat_llm/scripts/check_cuda.py` is the first GPU diagnostic.
- The F5 reference files live under `miguel_furhat_llm/assets/input/audio/` and
  must remain private.

If F5-TTS is not running, `miguellm serve` can autostart it only if
`MIGUELLM_TTS_START_COMMAND` and `MIGUELLM_TTS_CWD` are set correctly.

## TTS Troubleshooting Order

Use this order on Linux:

1. Check whether MiguelLM backend starts:
   ```bash
   miguellm serve --config config/server.yaml --host 127.0.0.1 --port 8765
   ```

2. Check backend health:
   ```bash
   curl http://127.0.0.1:8765/health
   ```

3. Check F5-TTS health directly:
   ```bash
   curl http://127.0.0.1:7861/health
   ```

4. If F5-TTS is down, check whether port 7861 is occupied before loading the
   model:
   ```bash
   ss -ltnp | grep 7861 || true
   lsof -i :7861 || true
   ```

5. In the Furhat repo, run CUDA diagnostics:
   ```bash
   cd /home/miguelsv/miguel/code/miguel_furhat_llm
   source .venv-f5/bin/activate
   python scripts/check_cuda.py
   ```

6. Start F5-TTS manually if needed:
   ```bash
   cd /home/miguelsv/miguel/code/miguel_furhat_llm
   source .venv-f5/bin/activate
   python scripts/f5_tts_server.py \
     --host 127.0.0.1 \
     --port 7861 \
     --device cuda \
     --nfe-step 16 \
     --speed 1.08 \
     --ref-audio assets/input/audio/f5_reference.wav \
     --ref-text-file assets/input/audio/f5_reference.txt
   ```

If `pip install f5-tts` succeeded but synthesis fails, check OS `ffmpeg`:

```bash
ffmpeg -version
```

Install it if missing:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

## Public Safety Rules

- `config/dev.yaml` is the public client config and must stay `backend.mode:
  remote`.
- Do not commit `.env`, `.env.local`, `memory/`, `sessions/`, private persona
  folders, voice WAVs, tokens, API keys, or private F5-TTS artifacts.
- Do not publish a raw Linux server IP. Use Cloudflare Tunnel or Tailscale Funnel.
- Keep checked-in persona content public-safe.
- Keep OpenAI dialogue/STT and local F5-TTS on the Linux backend by default.
- `MIGUELLM_BACKEND_TOKEN` is only an app access token, not a substitute for
  serious authentication.

## Important Files

- `src/miguel_lm/cli.py` — `miguellm` and `miguellm serve`
- `src/miguel_lm/server.py` — backend HTTP endpoints
- `src/miguel_lm/remote.py` — public client backend calls
- `src/miguel_lm/tts_supervisor.py` — optional F5-TTS autostart
- `config/dev.yaml` — public-safe client config
- `config/server.yaml` — private Linux backend config
- `docs/CLOUDFLARE_TUNNEL.md` — tunnel setup runbook

## Tests

Run:

```bash
python -m pytest -q
```

Tests should not require OpenAI, Cloudflare, the F5 server, or the Furhat robot.
