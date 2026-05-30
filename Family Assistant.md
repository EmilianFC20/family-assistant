# Chat Summary

We talked about building a Discord bot for a family smart-home helper that can answer questions from documentation.

## Main ideas
- A Discord bot can answer FAQ-style questions from a `FAQ.md` file.
- The FAQ file works best when it uses clear `##` question headings and concise answers.
- Instead of converting a manual into a FAQ, the bot can also search a Markdown manual directly.
- The bot does not run inside Discord. It runs as a Python program on your server and connects outward to Discord.
- You can host the Python code on your server, a Raspberry Pi, or another always-on machine.
- A more powerful setup is to have the Discord bot send questions to OpenWebUI, which then asks an LLM.
- In your setup, Ollama and OpenWebUI are running on your desktop, your manual is already uploaded there, and you created a custom model called `Family1`.
- The next steps are to create a Discord bot in the Discord Developer Portal, invite it to your server, and run a small Python bridge on your server.
- The Python bridge should send user questions to OpenWebUI and relay the answer back to Discord.

## Recommended next step
- Keep OpenWebUI as the knowledge and reasoning layer.
- Let the Discord bot stay small and only handle Discord messages and API calls.
- Add safety rules later if the bot will answer or control smart-home functions.

## Final setup we converged on
- Discord server: user interface for the family
- Python bot on your server: bridge between Discord and OpenWebUI
- OpenWebUI on your desktop: LLM and knowledge base
- Ollama on your desktop: model runtime behind OpenWebUI
