# Cloudflare Tunnel Setup For MiguelLM

Use this when you want public MiguelLM clients to reach your private Linux
backend without publishing the Linux server IP or opening inbound firewall
ports.

## Shape

```text
student laptop -> https://miguellm.your-domain.example
              -> Cloudflare Tunnel
              -> cloudflared on Linux
              -> http://127.0.0.1:8765
              -> miguellm serve
              -> OpenAI + local F5-TTS
```

The public GitHub/client side only needs:

```dotenv
MIGUELLM_BACKEND_URL=https://miguellm.your-domain.example
MIGUELLM_BACKEND_TOKEN=the-shared-app-token-if-enabled
```

The OpenAI key, private persona, private memory, and F5-TTS command stay only on
the Linux machine.

## 1. Linux Backend `.env.local`

First get the public MiguelLM code onto the Linux machine. Once this repository
is on GitHub:

```bash
cd /home/miguel/Code
git clone https://github.com/YOUR-USER/MiguelLM.git
cd MiguelLM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Before the repo is public, copy it from the Mac without runtime/private files:

```bash
rsync -av --exclude .venv --exclude .env --exclude .env.local --exclude memory --exclude sessions --exclude tmp \
  /Users/miguel/miguel/Code/miguelLM/ \
  linux-host:/home/miguel/Code/MiguelLM/
```

Then create `.env.local` in the MiguelLM checkout on the Linux machine:

```dotenv
OPENAI_API_KEY=your_openai_key_here
OPENAI_DIALOGUE_MODEL=gpt-5.4-mini
OPENAI_TRANSCRIBE_MODEL=whisper-1
LOCAL_TTS_ENDPOINT=http://127.0.0.1:7861/synthesize

# Use a long random value. Clients need this too, but it is not an OpenAI key.
MIGUELLM_BACKEND_TOKEN=replace-with-a-long-random-token

# Private persona lives outside the public Git checkout.
MIGUELLM_PERSONA_DIR=/home/miguel/private/miguellm-persona

# Optional F5-TTS autostart. Keep paths local to Linux.
MIGUELLM_TTS_CWD=/home/miguel/Code/miguel_furhat_llm
MIGUELLM_TTS_START_COMMAND=bash -lc 'source .venv-f5/bin/activate && python scripts/f5_tts_server.py --host 127.0.0.1 --port 7861 --device cuda --nfe-step 16 --speed 1.08 --ref-audio assets/input/audio/f5_reference.wav --ref-text-file assets/input/audio/f5_reference.txt'
```

Create the private persona folder before starting the backend. For a first run,
copy the public placeholder persona as a template, then edit it privately:

```bash
mkdir -p "$HOME/private/miguellm-persona"
cp persona/*.md "$HOME/private/miguellm-persona/"
```

Then set:

```dotenv
MIGUELLM_PERSONA_DIR=/home/YOUR_LINUX_USER/private/miguellm-persona
```

Do not commit this private persona folder. It should live outside the Git
checkout.

## 2. Start MiguelLM Backend Locally

```bash
cd /path/to/miguelLM
source .venv/bin/activate
miguellm serve --config config/server.yaml --host 127.0.0.1 --port 8765
```

Check it from the Linux machine:

```bash
curl http://127.0.0.1:8765/health
```

Expected shape:

```json
{"ok": true, "tts_healthy": true}
```

`tts_healthy` can be false while you debug F5-TTS, but the backend itself should
answer.

## 3. Install `cloudflared` On Linux

On Ubuntu/Debian:

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update
sudo apt-get install cloudflared
```

## 4. Create The Tunnel

One-time login:

```bash
cloudflared tunnel login
```

Create a named tunnel:

```bash
cloudflared tunnel create miguellm
```

Create `~/.cloudflared/config.yml`. Replace the UUID and path with the values
printed by `cloudflared tunnel create`:

```yaml
tunnel: YOUR-TUNNEL-UUID
credentials-file: /home/miguel/.cloudflared/YOUR-TUNNEL-UUID.json

ingress:
  - hostname: miguellm.your-domain.example
    service: http://127.0.0.1:8765
  - service: http_status:404
```

Create the DNS route:

```bash
cloudflared tunnel route dns miguellm miguellm.your-domain.example
```

Run the tunnel:

```bash
cloudflared tunnel run miguellm
```

Check from any machine:

```bash
curl https://miguellm.your-domain.example/health
```

## 5. Make `cloudflared` Persistent

After the tunnel works manually:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

If the service cannot find your config because `sudo` changes `$HOME`, install
or run it with an explicit config path according to Cloudflare's Linux service
instructions.

## 6. Client Setup

On a student/friend machine:

```bash
git clone https://github.com/YOUR-USER/MiguelLM.git
cd MiguelLM
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create `.env.local`:

```dotenv
MIGUELLM_BACKEND_URL=https://miguellm.your-domain.example
MIGUELLM_BACKEND_TOKEN=replace-with-the-shared-app-token
```

Run:

```bash
miguellm
```

## Safety Checks

- Do not use `--host 0.0.0.0` for `miguellm serve` unless you intentionally want LAN exposure.
- Do not publish the Linux machine IP.
- Do not commit `.env`, `.env.local`, private persona files, private voice files, or memory files.
- Keep `MIGUELLM_BACKEND_TOKEN` long and random if the URL is accessible to others.
- Treat the backend token as an app access token, not as a true replacement for serious authentication.
