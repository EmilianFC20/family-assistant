FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached separately from the source code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot source
COPY family_discord_openwebui_bot.py .

CMD ["python3", "family_discord_openwebui_bot.py"]
