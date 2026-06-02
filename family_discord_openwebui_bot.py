"""Discord bot that forwards questions to OpenWebUI and returns the answer.

Setup
-----
1. Install dependencies:
   pip install discord.py requests python-dotenv

   (or: pip install -r requirements.txt)

2. Create a `.env` file next to this script with:

   DISCORD_TOKEN=your_discord_bot_token
   OPENWEBUI_URL=http://localhost:8080           # bare base URL — script appends /api/chat/completions
   OPENWEBUI_MODEL=qwen3.5-tuned:latest
   OPENWEBUI_API_KEY=your_openwebui_api_key      # Settings → Account → API Keys in OpenWebUI

   IMPORTANT: OPENWEBUI_URL must be the bare base URL (no trailing slash, no path).
   The script builds the full endpoint as: {OPENWEBUI_URL}/api/chat/completions

3. In the Discord Developer Portal:
   - Create a bot application
   - Enable the Message Content Intent
   - Invite the bot to your server with Send Messages / Read Message History / Embed Links

4. Run:
   python3 family_discord_openwebui_bot.py

   Or with Docker Compose (see docker-compose.yml).

Notes
-----
- If your OpenWebUI instance uses a different API path or payload shape, adjust ASK_ENDPOINT and ask_openwebui().
- OpenWebUI uses the OpenAI-compatible chat completions endpoint (/api/chat/completions).
- An API key is required when OpenWebUI auth is enabled. Generate one under Settings → Account.
- This script is intentionally small and easy to adapt.
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Optional

import discord
import requests
from discord.ext import commands
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("family_bot")

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
OPENWEBUI_URL = os.getenv("OPENWEBUI_URL", "").rstrip("/")
OPENWEBUI_MODEL = os.getenv("OPENWEBUI_MODEL", "qwen3.5-tuned:latest")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY", "")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in .env")
if not OPENWEBUI_URL:
    raise RuntimeError("OPENWEBUI_URL is not set in .env")
if not OPENWEBUI_API_KEY:
    log.warning(
        "OPENWEBUI_API_KEY is not set. "
        "Requests will be sent without auth — this will fail if OpenWebUI auth is enabled. "
        "Generate a key under Settings → Account in OpenWebUI and add it to .env."
    )

# OpenWebUI uses the OpenAI-compatible chat completions endpoint.
# Previously this was /api/chat (wrong) — the correct path is /api/chat/completions.
ASK_ENDPOINT = f"{OPENWEBUI_URL}/api/chat/completions"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def ask_openwebui(question: str) -> str:
    """Send a question to OpenWebUI and return the model answer."""

    headers = {"Content-Type": "application/json"}
    if OPENWEBUI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENWEBUI_API_KEY}"

    payload = {
        "model": OPENWEBUI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a family smart-home assistant. "
                    "Answer clearly and briefly. "
                    "Use the uploaded house manual when relevant. "
                    "If you are unsure, say you do not know."
                ),
            },
            {"role": "user", "content": question},
        ],
        "stream": False,
    }

    log.info("POST %s  model=%s", ASK_ENDPOINT, OPENWEBUI_MODEL)
    response = requests.post(ASK_ENDPOINT, json=payload, headers=headers, timeout=90)

    if not response.ok:
        log.error(
            "OpenWebUI returned HTTP %d: %s",
            response.status_code,
            response.text[:400],
        )
    response.raise_for_status()

    data = response.json()

    # Try a few common response shapes so the script is easier to adapt.
    # OpenWebUI's /api/chat/completions returns the standard OpenAI shape:
    # {"choices": [{"message": {"content": "..."}}]}
    if isinstance(data, dict):
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"].strip()
        if "message" in data and isinstance(data["message"], dict):
            content = data["message"].get("content")
            if content:
                return str(content).strip()
        if "content" in data and isinstance(data["content"], str):
            return data["content"].strip()

    return str(data)


@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    log.info("OpenWebUI endpoint: %s", ASK_ENDPOINT)
    log.info("Model: %s", OPENWEBUI_MODEL)
    log.info("Bot is ready")


@bot.command(name="ask")
async def ask(ctx: commands.Context, *, question: str) -> None:
    """Ask the family assistant a question.

    Usage:
        !ask How do I turn on movie mode?
    """

    async with ctx.typing():
        try:
            answer = ask_openwebui(question)
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f" (HTTP {status})" if status else ""
            await ctx.send(f"Sorry, I could not reach OpenWebUI{detail}: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - show a friendly error message
            await ctx.send(f"Something went wrong: {exc}")
            return

    if not answer:
        await ctx.send("I did not get an answer back.")
        return

    # Discord message limit is 2000 characters.
    if len(answer) <= 2000:
        await ctx.send(answer)
        return

    # If the answer is long, split it into chunks.
    chunk_size = 1900
    for start in range(0, len(answer), chunk_size):
        await ctx.send(answer[start : start + chunk_size])


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    await ctx.send("pong")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
