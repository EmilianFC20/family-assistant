# Family Assistant

A Discord bot that bridges a family Discord server with a self-hosted [OpenWebUI](https://github.com/open-webui/open-webui) / [Ollama](https://ollama.com) stack. Ask it questions about the house, get answers grounded in your uploaded house manual.

```
Discord  →  bot (OMV server)  →  OpenWebUI (OMV server)  →  Ollama (desktop GPU)
```

The bot does no AI work itself — it only shuttles messages. All reasoning and knowledge live in OpenWebUI, backed by a custom model called `Family1` with the house manual as a knowledge base.

## Quick start

### 1. Prerequisites

| Component | Where it runs |
|---|---|
| Ollama (native Windows, GPU) | Desktop `10.73.73.9:11434` |
| OpenWebUI + bot (Docker Compose) | OMV server `10.73.73.10` |

See [Setup guide](#setup-guide) below for the one-time infrastructure steps.

### 2. Clone and configure

```bash
git clone https://github.com/EmilianFC20/family-assistant.git
cd family-assistant
cp .env.example .env
nano .env   # fill in DISCORD_TOKEN and OPENWEBUI_API_KEY
```

### 3. Run

```bash
docker compose up -d
docker compose logs -f bot
```

OpenWebUI is available at `http://<server-ip>:8080`.

## Bot commands

| Command | What it does |
|---|---|
| `!ask <question>` | Ask the family assistant; answer is grounded in the house manual |
| `!ping` | Health check — replies `pong` |

## Project files

```
family_discord_openwebui_bot.py   # the bot — the only production code
requirements.txt                  # Python deps
Dockerfile                        # bot container image
docker-compose.yml                # OpenWebUI + bot, wired together
.env.example                      # .env template
```

## Setup guide

### Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application → Bot tab → copy the **Token** into `.env` as `DISCORD_TOKEN`.
3. Enable **Message Content Intent** (Bot → Privileged Gateway Intents).
4. Invite the bot with **Send Messages**, **Read Message History**, **Embed Links**.

### Ollama on the desktop (one-time)

1. Install [Ollama for Windows](https://ollama.com/download/windows) — it detects NVIDIA GPUs automatically.
2. Add a system environment variable `OLLAMA_HOST=0.0.0.0:11434`, then restart Ollama.
3. Add a Windows Defender Firewall inbound rule: TCP port `11434`, scoped to your LAN subnet only.
4. Pull your base model: `ollama pull <model-name>`.

### OpenWebUI on the server

The `docker-compose.yml` in this repo runs OpenWebUI pointed at Ollama on the desktop. Before the first `docker compose up`:

1. **Migrate your existing data volume** (house manual, model definitions, accounts):
   ```bash
   # On the old machine (WSL/desktop), back up:
   docker run --rm -v open-webui:/data -v $PWD:/backup alpine \
     tar czf /backup/owui-data.tgz -C /data .
   scp owui-data.tgz user@<server>:~/family-assistant/

   # On the server, restore:
   docker volume create open-webui
   docker run --rm -v open-webui:/data -v $PWD:/backup alpine \
     tar xzf /backup/owui-data.tgz -C /data
   ```
2. `docker compose up -d`

### OpenWebUI API key

1. Open `http://<server-ip>:8080`, sign in.
2. **Settings → Account → API Keys → Generate**.
3. Add to `.env`: `OPENWEBUI_API_KEY=sk-...`
4. `docker compose up -d` (restart the bot with the key).

## Architecture notes

- **Outbound-only**: the bot dials out to Discord and OpenWebUI; nothing connects inward. Do not add inbound listeners without revisiting this.
- **No WSL networking**: Ollama runs natively on Windows (not inside WSL) so the GPU is used directly and there is no dynamic-IP / `netsh portproxy` problem.
- **Endpoint**: the bot uses OpenWebUI's OpenAI-compatible `/api/chat/completions` endpoint with a Bearer token.
- **`Family1` model**: the system prompt and house-manual knowledge collection are stored in the OpenWebUI data volume (`/app/backend/data`), not in Ollama. They travel with the volume backup.

## Development

```bash
pip install -r requirements.txt
# Set OPENWEBUI_URL=http://10.73.73.10:8080 in .env for local dev
python3 family_discord_openwebui_bot.py
```
