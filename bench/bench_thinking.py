#!/usr/bin/env python3
"""Section 3 of BENCHMARKS.md — why `think: false` is mandatory on the Family1 model.

Tests the claim recorded in CLAUDE.md: with the big system prompt plus RAG chunks inside
`num_ctx 4096`, the reasoning trace blows the token budget, giving ~100 s latency and
empty or truncated answers.

Two conditions per model:
  1. context deliberately filled to num_ctx (the real RAG path)
  2. a short unconstrained prompt (for contrast — thinking is cheap here)

    python3 bench/bench_thinking.py
"""
import time

import requests

HOST = "http://127.0.0.1:11434"
MODELS = ["qwen3.5-4b-tuned:latest", "qwen3.5-tuned:latest"]
REPEATS = 2

SYSTEM = (
    "Eres un asistente encargado de ayudar a una familia a entender mejor la funcionalidad "
    "de su casa inteligente. Tu objetivo es ayudarles a resolver problemas y responder "
    "preguntas utilizando la informacion de la documentacion que te sera proporcionada. "
    "Por favor se amable, paciente y educado al responder."
)

# Synthetic manual chunks, repeated to fill the context. The real RAG path retrieves
# 1,547-2,284 prompt tokens; this deliberately overfills to num_ctx to expose the failure.
CHUNK = (
    "El foco inteligente de la sala se conecta a la red de 2.4 GHz llamada CasaFC. "
    "Para reiniciarlo, apagalo y prendelo tres veces seguidas hasta que parpadee. "
    "El enchufe inteligente de la cocina usa la app Tuya y su contrasena es la del router. "
)

QUESTION = "Como reconecto un enchufe inteligente que se cayo de la red?"


def unload(model):
    requests.post(f"{HOST}/api/generate",
                  json={"model": model, "keep_alive": 0}, timeout=120)
    time.sleep(4)


def generate(model, prompt, think):
    t0 = time.perf_counter()
    d = requests.post(f"{HOST}/api/generate",
                      json={"model": model, "prompt": prompt, "stream": False,
                            "think": think,
                            "options": {"temperature": 0.7, "seed": 42}},
                      timeout=1800).json()
    return time.perf_counter() - t0, d


def report(label, model, prompt):
    print(f"\n--- {label}: {model} ---")
    for think in (False, True):
        unload(model)
        for i in range(REPEATS):
            wall, d = generate(model, prompt, think)
            reasoning = d.get("thinking") or ""
            answer = d.get("response") or ""
            flag = "  <-- EMPTY/TRUNCATED" if len(answer) < 40 else ""
            print(f"  think={str(think):5s} #{i}  wall {wall:7.2f}s  "
                  f"prompt_tok {d.get('prompt_eval_count', 0):5d}  "
                  f"out_tok {d.get('eval_count', 0):5d}  "
                  f"reasoning {len(reasoning):6d}ch  answer {len(answer):5d}ch{flag}")


def main():
    full_context = f"{SYSTEM}\n\nDocumentacion:\n{CHUNK * 95}\n\nPregunta: {QUESTION}"
    for model in MODELS:
        report("context filled to num_ctx (the RAG path)", model, full_context)
    for model in MODELS:
        report("short unconstrained prompt (contrast)", model, QUESTION)

    print("\nExpected: with a full context, think=true costs ~50-93 s and can return an "
          "empty answer,\nwhile think=false answers in ~4-7 s. On a short prompt thinking "
          "is merely slower, not fatal.")


if __name__ == "__main__":
    main()
