# Family Assistant

A Discord bot that bridges a family Discord server with a self-hosted [OpenWebUI](https://github.com/open-webui/open-webui) / [Ollama](https://ollama.com) stack. Ask it questions about the house, get answers grounded in your uploaded house manual.

```
Discord  →  bot (WSL2)  →  OpenWebUI (WSL2)  →  Ollama (WSL2, desktop GPU)
```

The whole stack runs in WSL2 on the desktop (`10.73.73.9`), where the RTX 3070 Ti lives. The bot does no AI work itself — it only shuttles messages. All reasoning and knowledge live in OpenWebUI, backed by a custom model (`Family1`, engine `qwen3.5-4b-tuned` — a 4B sized to fit the 3070 Ti's 8 GB at 100% GPU) with the house manual as a knowledge base.

> Looking for *why* it's wired this way (NAT vs mirrored, native Ollama vs Docker, the portproxy)? See **CLAUDE.md → Design decisions & justifications**.

## Quick start

### 1. Prerequisites (already set up — for reference)

| Component | Where it runs |
|---|---|
| Ollama (native systemd, GPU/CUDA) | WSL2 on desktop — `0.0.0.0:11434` |
| OpenWebUI (Docker, host networking) | WSL2 on desktop — `:8080`, started from `/opt/docker-compose.yaml` |
| Family Assistant bot (Docker, host networking) | WSL2 on desktop — this repo |
| Nginx Proxy Manager (public domain) | OMV server `10.73.73.10` → `asistente.emilian.website` → `10.73.73.9:8080` |

WSL2 uses **NAT** networking; LAN access is preserved via a Windows `netsh portproxy` refreshed each boot by the "WSL portproxy" scheduled task. (Do **not** switch WSL to mirrored mode — see CLAUDE.md.)

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

OpenWebUI is at `http://localhost:8080` (or `https://asistente.emilian.website`).

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
docker-compose.yml                # the bot (host networking); OpenWebUI runs separately
.env.example                      # .env template
qwen-family-4b.Modelfile          # the Ollama engine definition (4B, num_ctx 4096)
BENCHMARKS.md                     # measured performance — the source the blog posts cite
bench/                            # the scripts that produce BENCHMARKS.md
```

## Performance

Measured on the RTX 3070 Ti, not estimated — see **[BENCHMARKS.md](BENCHMARKS.md)**. Warm answers
land in **3–6 s** end to end through OpenWebUI (fastest 2.3 s, genuine cold start 9.8 s), the 4B
engine generates at **103 tok/s**, and it leaves 1.4–2.2 GB of VRAM free where the old 9.7B engine
left 271 MiB. That headroom, not the parameter count, is why the 4B is the production engine.

## Setup guide

### Discord bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application → Bot tab → copy the **Token** into `.env` as `DISCORD_TOKEN`.
3. Enable **Message Content Intent** (Bot → Privileged Gateway Intents).
4. Invite the bot with **Send Messages**, **Read Message History**, **Embed Links**.

### Ollama (already running in WSL)

Native systemd service. Listens on `0.0.0.0:11434`, uses the RTX 3070 Ti via CUDA. Manage with
`systemctl status ollama`. Verify the GPU is in use with `ollama ps` (`PROCESSOR = 100% GPU`).

### OpenWebUI (already running in WSL)

Docker container `open-webui` (`network_mode: host`), started from `/opt/docker-compose.yaml` with
`OLLAMA_BASE_URL=http://0.0.0.0:11434`. Its data volume holds the house manual, the model definition,
and accounts — **back it up before any teardown**:

```bash
docker run --rm -v open-webui:/data -v $PWD:/backup alpine \
  tar czf /backup/owui-data.tgz -C /data .
```

### OpenWebUI API key

1. Open `http://localhost:8080`, sign in.
2. **Settings → Account → API Keys → Generate**.
3. Add to `.env`: `OPENWEBUI_API_KEY=sk-...`
4. `docker compose up -d` (restart the bot with the key).

## Architecture notes

- **Outbound-only**: the bot dials out to Discord and OpenWebUI; nothing connects inward.
- **All in WSL2 on the desktop**: Ollama needs the desktop GPU; OpenWebUI + bot are co-located with
  `network_mode: host` to reach it over `localhost`. The OMV server (1.8 GB RAM) only runs NPM.
- **NAT, not mirrored**: mirrored mode broke `127.0.0.1` loopback (Ollama GPU discovery) and the VPN;
  NAT fixes both. LAN access uses a portproxy auto-refreshed on each boot.
- **Endpoint**: the bot uses OpenWebUI's OpenAI-compatible `/api/chat/completions` with a Bearer token.
- **Model lives in OpenWebUI**: the system prompt + house-manual knowledge collection are in the
  OpenWebUI data volume (`/app/backend/data`), not in Ollama.

## Development

```bash
pip install -r requirements.txt
# OPENWEBUI_URL=http://localhost:8080 in .env
python3 family_discord_openwebui_bot.py
```
