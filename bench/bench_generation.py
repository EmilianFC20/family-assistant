#!/usr/bin/env python3
"""Sections 1 and 2 of BENCHMARKS.md — generation speed and VRAM headroom.

Measures, per model: time to first token, generation rate, prompt processing rate,
cold-load time, and the absolute VRAM the card is holding once the model is resident.

Rates come from Ollama's own counters (eval_count / eval_duration), not from wall time,
so they are not polluted by HTTP overhead.

    python3 bench/bench_generation.py [model ...]
"""
import json
import subprocess
import sys
import time

import requests

HOST = "http://127.0.0.1:11434"
REPEATS = 3

PROMPTS = [
    ("short", "In one sentence, what is the Wi-Fi password used for?"),
    ("medium", "Explain in about 150 words how to reconnect a smart plug that dropped "
               "off the home Wi-Fi network."),
    ("long", "Write roughly 400 words explaining, for a non-technical family member, what "
             "a self-hosted AI assistant is, why it runs on a home PC instead of the cloud, "
             "and what that means for their privacy."),
]

MODELS = sys.argv[1:] or [
    "qwen3.5-4b-tuned:latest",
    "qwen3.5:4b",
    "llama3.2:latest",
    "qwen3.5-tuned:latest",
]


def nvidia(field):
    out = subprocess.run(["nvidia-smi", f"--query-gpu={field}",
                          "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0])


def unload(model):
    requests.post(f"{HOST}/api/generate",
                  json={"model": model, "keep_alive": 0}, timeout=120)
    time.sleep(4)


def ps_line(model):
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        if model.split(":")[0] in line:
            return " ".join(line.split())
    return ""


def run(model, prompt):
    """One streaming request. Returns metrics in seconds and tokens."""
    body = {"model": model, "prompt": prompt, "stream": True, "think": False,
            "options": {"temperature": 0.7, "seed": 42}}
    t0 = time.perf_counter()
    ttft = None
    final = None
    with requests.post(f"{HOST}/api/generate", json=body, stream=True, timeout=1800) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            d = json.loads(line)
            if ttft is None and d.get("response"):
                ttft = time.perf_counter() - t0
            if d.get("done"):
                final = d
    ns = 1e9
    return {
        "ttft_s": ttft,
        "load_s": final.get("load_duration", 0) / ns,
        "prompt_tokens": final.get("prompt_eval_count", 0),
        "prompt_s": final.get("prompt_eval_duration", 0) / ns,
        "eval_tokens": final.get("eval_count", 0),
        "eval_s": final.get("eval_duration", 0) / ns,
    }


def main():
    total_vram = nvidia("memory.total")
    for m in MODELS:
        unload(m)
    idle = nvidia("memory.used")
    print(f"# GPU total {total_vram} MiB | desktop at rest {idle} MiB")
    print("# NOTE: the desktop's share drifts (measured 434 MiB quiet, ~1,300 MiB in use).\n")

    results = {}
    for model in MODELS:
        print(f"\n{'=' * 72}\n{model}\n{'=' * 72}")
        unload(model)
        try:
            cold = run(model, PROMPTS[0][1])
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        resident = nvidia("memory.used")
        print(f"  cold load     : {cold['load_s']:.2f} s")
        print(f"  VRAM absolute : {resident} MiB   (free {total_vram - resident} MiB)")
        print(f"  ollama ps     : {ps_line(model)}")

        runs = []
        for name, prompt in PROMPTS:
            for i in range(REPEATS):
                m = run(model, prompt)
                runs.append(m)
                gen = m["eval_tokens"] / m["eval_s"] if m["eval_s"] else 0
                pp = m["prompt_tokens"] / m["prompt_s"] if m["prompt_s"] else 0
                print(f"  {name:6s} #{i}  TTFT {m['ttft_s']:.3f}s  "
                      f"gen {gen:6.2f} tok/s ({m['eval_tokens']:4d} tok)  "
                      f"prompt {pp:8.1f} tok/s")

        results[model] = {
            "cold_load_s": cold["load_s"],
            "vram_absolute_mib": resident,
            "vram_free_mib": total_vram - resident,
            "runs": runs,
        }
        unload(model)

    def median(values):
        values = sorted(values)
        return values[len(values) // 2] if values else 0

    print(f"\n\n{'=' * 96}\nSUMMARY (warm, median of {REPEATS} runs per prompt size)\n{'=' * 96}")
    print(f"{'model':<26}{'gen tok/s':>11}{'prompt tok/s':>14}{'TTFT':>9}"
          f"{'cold load':>11}{'VRAM abs':>10}{'free':>9}")
    for model, e in results.items():
        gens = [r["eval_tokens"] / r["eval_s"] for r in e["runs"] if r["eval_s"]]
        pps = [r["prompt_tokens"] / r["prompt_s"] for r in e["runs"] if r["prompt_s"]]
        ttfts = [r["ttft_s"] for r in e["runs"] if r["ttft_s"]]
        print(f"{model:<26}{median(gens):>11.2f}{median(pps):>14.1f}"
              f"{median(ttfts):>8.3f}s{e['cold_load_s']:>10.2f}s"
              f"{e['vram_absolute_mib']:>10}{e['vram_free_mib']:>9}")


if __name__ == "__main__":
    main()
