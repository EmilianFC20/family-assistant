# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Discord bot that acts as a thin bridge between a family Discord server and a self-hosted
OpenWebUI/Ollama instance. The bot itself does no AI work — it only handles Discord messages and
HTTP calls. All knowledge and reasoning live in OpenWebUI, backed by a custom Ollama model called
`Family1` that has the house manual uploaded as a knowledge base.

## Architecture

```
Family Discord server          (user-facing UI)
        ↓  !ask <question>
family_discord_openwebui_bot.py  (bridge, Docker container on OMV server 10.73.73.10)
        ↓  POST /api/chat/completions  Authorization: Bearer <key>
OpenWebUI  (Docker on OMV server 10.73.73.10:8080)   (LLM + house-manual knowledge base)
        ↓  OLLAMA_BASE_URL=http://10.73.73.9:11434
Ollama  (native Windows on desktop 10.73.73.9:11434)  (model runtime, RTX 3070 Ti GPU)
```

**Key design property — outbound-only**: the bot dials *out* to Discord and to OpenWebUI; nothing
ever connects *into* the server. This is intentional for privacy and was chosen over WhatsApp
(official Cloud API requires an inbound webhook; unofficial libs carry ToS/ban risk + Node.js
dependency). Do not add inbound listeners or a second messaging platform without revisiting this.

**Why OpenWebUI is on the OMV server, not the desktop**: OpenWebUI was previously running in
Docker inside WSL2 on the desktop. WSL2 assigns a dynamic NAT IP (`172.25.x.x`) that changes on
every reboot, which caused a hard-coded `netsh` portproxy to go stale and break LAN access. The
OMV server (`10.73.73.10`) has a stable IP and native Docker, eliminating that problem entirely.

**Why Ollama runs natively on Windows**: the RTX 3070 Ti is on the desktop; native Windows Ollama
uses the GPU directly without WSL networking layers.

**Request flow in the code**:
`!ask <question>` → `ask_openwebui()` POSTs a system+user chat payload to `ASK_ENDPOINT` →
response is parsed defensively across three JSON shapes (`choices[0].message.content`,
`message.content`, `content`) → answer chunked to Discord's 2 000-character limit and sent.

## Files

| File | Purpose |
|---|---|
| `family_discord_openwebui_bot.py` | The bot — the only production code |
| `requirements.txt` | Python dependencies (pinned major versions) |
| `Dockerfile` | Container image for the bot |
| `docker-compose.yml` | Runs OpenWebUI + bot together on the OMV server |
| `.env.example` | Template for the required `.env` file |
| `.gitignore` | Keeps `.env` (secrets) out of version control |

## Setup & Running

### Quickstart (Docker Compose on the OMV server)

```bash
# 1. Clone / copy the repo onto the OMV server
scp -r . user@10.73.73.10:~/family-assistant

# 2. Create .env from the template and fill in your values
cp .env.example .env
nano .env

# 3. Start everything
docker compose up -d

# 4. Tail logs
docker compose logs -f bot
```

### .env values

```
DISCORD_TOKEN=your_discord_bot_token
OPENWEBUI_URL=http://open-webui:8080   # Docker service name — works inside compose
OPENWEBUI_MODEL=Family1
OPENWEBUI_API_KEY=your_openwebui_api_key
```

### Running without Docker (manual / dev)

```bash
pip install -r requirements.txt
# .env must point OPENWEBUI_URL at the real host, e.g. http://10.73.73.10:8080
python3 family_discord_openwebui_bot.py
```

## Discord Developer Portal requirements

Enable **Message Content Intent**; invite the bot with **Send Messages**, **Read Message History**,
and **Embed Links**.

Bot commands: `!ask <question>`, `!ping`.

## One-time migration / setup steps

These steps are performed once and are not part of the normal deploy cycle.

### Part C — Migrate Ollama to native Windows on the desktop (10.73.73.9)

1. Download and install **Ollama for Windows** from https://ollama.com/download/windows.
   It detects NVIDIA GPUs automatically and uses CUDA.

2. Migrate models:
   - **Option A (faster):** copy the WSL model store to Windows:
     ```
     # In WSL:
     cp -r ~/.ollama/models /mnt/c/Users/<YourUser>/.ollama/models
     ```
   - **Option B (simpler):** let Ollama re-download the base model after step 3 (`ollama pull <model>`).
   - Note: the `Family1` model *definition* (system prompt + knowledge binding) lives in
     OpenWebUI's data volume, not in Ollama. Only the underlying base model weights are in Ollama.

3. Make Ollama listen on the LAN — add a Windows **system** environment variable, then restart:
   ```
   Variable name:  OLLAMA_HOST
   Variable value: 0.0.0.0:11434
   ```
   (Win+R → `sysdm.cpl` → Advanced → Environment Variables → System variables → New)

4. Add a Windows Defender Firewall inbound rule:
   - Protocol: TCP, Port: 11434
   - Scope → Remote IP: **10.73.73.0/24** (LAN only, not Any)
   - Action: Allow

5. Verify from the OMV server:
   ```bash
   curl http://10.73.73.9:11434/api/tags
   # Should return JSON with {"models": [...]}
   ```

### Part D — Migrate OpenWebUI data to the OMV server and deploy

The OpenWebUI data volume contains the uploaded house manual, the `Family1` model definition, and
user accounts. Back it up before tearing down the old install.

**On the desktop (WSL), back up the volume:**
```bash
docker run --rm \
  -v open-webui:/data \
  -v $PWD:/backup \
  alpine tar czf /backup/owui-data.tgz -C /data .
# owui-data.tgz now holds the full data volume
```

**Copy the tarball to the OMV server:**
```bash
scp owui-data.tgz user@10.73.73.10:~/family-assistant/
```

**On the OMV server, restore before first `docker compose up`:**
```bash
docker volume create open-webui
docker run --rm \
  -v open-webui:/data \
  -v $PWD:/backup \
  alpine tar xzf /backup/owui-data.tgz -C /data
```

Then run `docker compose up -d`. OpenWebUI starts at `http://10.73.73.10:8080` with all existing
data intact (house manual, model, accounts).

### Part E — Generate an OpenWebUI API key

1. Open `http://10.73.73.10:8080` in a browser and sign in.
2. Go to **Settings → Account → API Keys → Generate new key**.
3. Copy the key and add it to `.env`: `OPENWEBUI_API_KEY=sk-...`
4. `docker compose up -d` — restarts the bot with the new key.
5. Confirm in **Workspace → Models** that `Family1` is listed and the house manual is still attached.

### Part F — Remove the old WSL portproxy plumbing

Run these in an **Administrator** PowerShell on the desktop once the new setup is verified:
```powershell
# Remove the port forward that was keeping OpenWebUI accessible from the LAN
netsh interface portproxy delete v4tov4 listenport=8080 listenaddress=0.0.0.0

# Optional: remove the Windows firewall rule for port 8080
# (check Windows Defender Firewall first before deleting)
```

In WSL, remove the old UFW rule and stop the old containers:
```bash
sudo ufw delete allow 8080
docker stop open-webui && docker rm open-webui
# Optionally remove the old WSL Ollama container / service too
```

## Verification checklist

1. **Ollama reachable from server:**
   ```bash
   curl http://10.73.73.9:11434/api/tags
   # Expect: {"models": [...]}
   ```

2. **OpenWebUI → Ollama:** open `http://10.73.73.10:8080`, send a chat to `Family1`, get a
   grounded answer from the house manual.

3. **API endpoint (the bug that was fixed):**
   ```bash
   curl -X POST http://10.73.73.10:8080/api/chat/completions \
     -H "Authorization: Bearer $OPENWEBUI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"Family1","messages":[{"role":"user","content":"test"}],"stream":false}'
   # Expect: {"choices":[{"message":{"content":"..."}}]}
   ```

4. **Bot is connected:**
   ```bash
   docker compose logs -f bot
   # Expect: "Logged in as ...  Bot is ready"
   ```

5. **Discord commands:** `!ping` → `pong`; `!ask How do I turn on movie mode?` → answer from the
   house manual.

6. **Reboot resilience:** reboot the desktop. No portproxy step needed. The server must still
   reach `http://10.73.73.9:11434/api/tags`. This was the original recurring problem — it is fixed.

## Gotchas

- **`OPENWEBUI_URL` must be the bare base URL** — do not include a path. The script appends
  `/api/chat/completions` itself. Setting it to `http://open-webui:8080/api/chat/completions`
  would produce `.../api/chat/completions/api/chat/completions`.

- **`/api/chat` was the wrong endpoint** — the original code used `/api/chat` (an internal Ollama
  proxy route). The correct OpenAI-compatible route is `/api/chat/completions`. This is now fixed.

- **`Family1` lives in OpenWebUI, not Ollama** — Ollama holds the raw base model weights.
  The `Family1` model definition (system prompt + knowledge collection binding) is stored in the
  OpenWebUI database (`/app/backend/data`). It travels with the data volume, not with Ollama.

- **WSL Ollama causes network instability** — if Ollama is reinstalled inside WSL, the dynamic-IP
  problem returns. Keep Ollama on native Windows on the desktop.

- **OpenWebUI auth requires an API key** — `/api/chat/completions` returns `401 Unauthorized` if
  auth is enabled and no `Authorization: Bearer <key>` header is sent. The bot logs a warning at
  startup if `OPENWEBUI_API_KEY` is empty. Generate a key as described in Part E above.
