# MiguelLM

A standalone terminal version of Miguel's lab clone. It does not require Furhat
or Virtual Furhat: people can type, or use push-to-talk microphone input, and the
app responds with text plus speech from Miguel's private Linux backend.

The public client does **not** need OpenAI secrets. By default, `miguellm`
connects to a private MiguelLM backend on the Linux machine. That backend holds
`OPENAI_API_KEY`, talks to local F5-TTS, and can start F5-TTS if it is down.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Public client settings can go in `.env`. Use a tunnel hostname, not a raw
server IP:

```dotenv
MIGUELLM_BACKEND_URL=https://miguellm.example.com
MIGUELLM_BACKEND_TOKEN=optional_shared_app_token
```

Do not put `OPENAI_API_KEY` in the public/client checkout.

## Run

```bash
miguellm
```

Type into the input bar and press Enter. Use `/help` inside the app for commands.
Push-to-talk is available with `ctrl+r` when OpenAI transcription is configured.
`miguellm run --config config/dev.yaml` is equivalent when you want to pass an
explicit config path.

Useful checks:

```bash
miguellm validate-persona --config config/dev.yaml
miguellm test-tts --config config/dev.yaml --text "Hello, this is Miguel's local terminal voice."
miguellm audio-devices --config config/dev.yaml
miguellm test-audio-input --config config/dev.yaml --transcribe
```

## Local Voice

The Linux backend uses the same local HTTP F5-TTS contract as
`miguel_furhat_llm`:
`POST /synthesize` with JSON `{"text": "..."}` and a WAV response. The health
probe is `GET /health` on the same host.

On the Linux machine, create `.env` or `.env.local` with private values:

```dotenv
OPENAI_API_KEY=your_openai_key_here
OPENAI_DIALOGUE_MODEL=gpt-5.4-mini
OPENAI_TRANSCRIBE_MODEL=whisper-1
LOCAL_TTS_ENDPOINT=http://127.0.0.1:7861/synthesize
MIGUELLM_BACKEND_TOKEN=optional_shared_app_token
MIGUELLM_PERSONA_DIR=/path/to/private/miguellm-persona

# Optional: let `miguellm serve` start F5-TTS if /health is offline.
MIGUELLM_TTS_CWD=/path/to/miguel_furhat_llm
MIGUELLM_TTS_START_COMMAND=bash -lc 'source .venv-f5/bin/activate && python scripts/f5_tts_server.py --host 127.0.0.1 --port 7861 --device cuda --nfe-step 16 --speed 1.08 --ref-audio assets/input/audio/f5_reference.wav --ref-text-file assets/input/audio/f5_reference.txt'
```

Start the private backend on Linux, bound to localhost:

```bash
miguellm serve --config config/server.yaml --host 127.0.0.1 --port 8765
```

Then expose it through a tunnel rather than opening a firewall port.

Recommended: Cloudflare Tunnel. `cloudflared` runs on the Linux machine and
creates an outbound-only tunnel to Cloudflare, so the origin machine does not
need a public routable IP or inbound port forwarding.

For the full setup, see [docs/CLOUDFLARE_TUNNEL.md](docs/CLOUDFLARE_TUNNEL.md).
The stable setup is a named Cloudflare Tunnel routing
`https://miguellm.your-domain.example` to `http://127.0.0.1:8765`. The public
client sets `MIGUELLM_BACKEND_URL` to that HTTPS hostname.

Alternative: Tailscale Funnel can publish a local service through a Tailscale
Funnel URL. That also avoids publishing the Linux machine's raw IP.

If `MIGUELLM_BACKEND_TOKEN` is set on the server, clients must set the same app
token locally. This token is not an OpenAI secret, but still should not be
committed.

The checked-in `persona/` folder is a public-safe placeholder. Put the real
Miguel persona on the Linux machine outside this Git checkout, then set
`MIGUELLM_PERSONA_DIR` to that folder before starting `miguellm serve`.

## Privacy

Durable memories are opt-in and are stored by the backend, not in the public
client. The app will not write durable memories until `/memory on` is used.
Transcripts, memories, private persona folders, and private voice assets are
git-ignored.
