#!/usr/bin/env python3
"""Section 4 of BENCHMARKS.md — what the family actually feels.

Times whole questions through the real path: Open WebUI's /api/chat/completions against
the Family1 model, with the house manual attached as a knowledge collection. This is the
only measurement that includes retrieval, so it is the one the blog posts quote.

Reads OPENWEBUI_URL / OPENWEBUI_MODEL / OPENWEBUI_API_KEY from .env.

    python3 bench/bench_endtoend.py            # warm timings only
    python3 bench/bench_endtoend.py --cold     # also measure a genuine cold start

--cold restarts the open-webui container to clear its caches. It comes back on its own
(restart: always), but do not run it while somebody is asking the assistant something.
"""
import os
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPEATS = 3

QUESTIONS = [
    ("wifi", "What is the Wi-Fi password?"),
    ("device", "How do I reconnect a smart plug that fell off the network?"),
    ("general", "Which streaming services do we have at home?"),
]


def load_env():
    env = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit(f"No .env at {path}. Copy .env.example and fill it in.")
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for key in ("OPENWEBUI_URL", "OPENWEBUI_MODEL", "OPENWEBUI_API_KEY"):
        if not env.get(key):
            sys.exit(f"{key} is missing from .env")
    return env


def ask(env, question):
    t0 = time.perf_counter()
    r = requests.post(
        f"{env['OPENWEBUI_URL'].rstrip('/')}/api/chat/completions",
        headers={"Authorization": f"Bearer {env['OPENWEBUI_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": env["OPENWEBUI_MODEL"],
              "messages": [{"role": "user", "content": question}]},
        timeout=600)
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    d = r.json()
    usage = d.get("usage", {})
    return elapsed, d["choices"][0]["message"]["content"], usage


def cold_start(env):
    """Unload the engine and restart Open WebUI, then time the first real question."""
    print("Unloading the Ollama engine and restarting open-webui...")
    requests.post("http://127.0.0.1:11434/api/generate",
                  json={"model": "qwen3.5-4b-tuned:latest", "keep_alive": 0}, timeout=120)
    subprocess.run(["docker", "restart", "open-webui"], capture_output=True)

    base = env["OPENWEBUI_URL"].rstrip("/")
    for _ in range(120):
        try:
            if requests.get(f"{base}/health", timeout=3).status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        sys.exit("open-webui did not come back healthy")
    time.sleep(3)

    print("open-webui is up. Timing a genuine cold start (engine load + first RAG):\n")
    for i in range(4):
        elapsed, answer, usage = ask(env, QUESTIONS[1][1])
        label = "COLD" if i == 0 else "warm"
        print(f"  request #{i} ({label:4s})  {elapsed:7.2f}s  "
              f"prompt_tok {usage.get('prompt_tokens')}  "
              f"out_tok {usage.get('completion_tokens')}  answer {len(answer)}ch")


def main():
    env = load_env()
    print(f"Model: {env['OPENWEBUI_MODEL']} at {env['OPENWEBUI_URL']}\n")

    if "--cold" in sys.argv:
        cold_start(env)
        print()

    print("Warm timings:\n")
    timings = []
    for name, question in QUESTIONS:
        for i in range(REPEATS):
            elapsed, answer, usage = ask(env, question)
            timings.append(elapsed)
            print(f"  {name:8s} #{i}  {elapsed:7.2f}s  "
                  f"prompt_tok {usage.get('prompt_tokens')}  "
                  f"out_tok {usage.get('completion_tokens')}  answer {len(answer)}ch")

    timings.sort()
    print(f"\n  fastest {timings[0]:.1f}s | median {timings[len(timings) // 2]:.1f}s "
          f"| slowest {timings[-1]:.1f}s")


if __name__ == "__main__":
    main()
