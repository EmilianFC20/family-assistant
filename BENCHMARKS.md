# Benchmarks — measured, not remembered

Every number in this file was measured on the machine, not recalled. It exists so the blog
posts ([part 1](https://emilian.website/posts/deploy-private-ai-ollama/),
[part 2](https://emilian.website/posts/discord-bot-private-ai-assistant/)) and
[`CLAUDE.md`](CLAUDE.md) can cite a source instead of a memory.

**Measured 2026-08-11.** Re-run the scripts in [`bench/`](bench/) to refresh.

## Test machine

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 3070 Ti, 8 GB (8,192 MiB) |
| Windows NVIDIA driver | 595.79 |
| CUDA reported in WSL | 13.2 |
| Ollama | 0.24.0, native systemd service inside WSL2 |
| Open WebUI | `ghcr.io/open-webui/open-webui:main`, Docker, `--network=host` |
| Host | desktop `10.73.73.9`; Portainer server + NPM on OMV `10.73.73.10` |

**The Windows desktop's VRAM use is not constant**: it measured **434 MiB** during a quiet
session and **1,295–1,326 MiB** while the machine was in use. This drift matters more than its
size, and is the mechanism behind the spill described below.

## 1. Generation speed

Ollama HTTP API `/api/generate`, streaming, `think: false`, `temperature 0.7`, `seed 42`.
Three prompt sizes (25/36/58 prompt tokens → ~34/~185/~530 output tokens), 3 repeats each,
model unloaded before each cold-start measurement. Rates are Ollama's own counters
(`eval_count / eval_duration`), median reported.

| model | params | generation | prompt processing | TTFT | cold load | VRAM absolute |
|---|---|---|---|---|---|---|
| `llama3.2` | 3.2B Q4_K_M | **195 tok/s** | 7,370 tok/s | 0.10 s | 4.4 s | 3,017 MiB |
| `qwen3.5-4b-tuned` | 4.7B Q4_K_M | **103 tok/s** | 798 tok/s | 0.20 s | 4.2 s | 5,949 MiB |
| `qwen3.5:4b` | 4.7B Q4_K_M | 102 tok/s | 513 tok/s | 0.22 s | 3.4 s | (same weights) |
| `qwen3.5-tuned` | 9.7B Q4_K_M | **70 tok/s** | 780 tok/s | 0.20 s | 6.4 s | 7,921 MiB |

VRAM is an absolute `nvidia-smi` reading from a quiet session (desktop at 434 MiB included).

- Generation rate is **flat with output length**: the 4B held 101–105 tok/s from 34 to 534 tokens.
- The Modelfile tuning costs nothing: tuned 4B 103 tok/s vs stock 4B 102 tok/s.

## 2. VRAM headroom — why the engine is a 4B

| | model footprint | absolute used | free |
|---|---|---|---|
| `llama3.2` 3.2B | 2,583 MiB | 3,017 MiB | 5,175 MiB |
| `qwen3.5-4b-tuned` 4.7B (`num_ctx 4096`) | **5,515 MiB fixed** | 5,949 MiB | **2,243 MiB** |
| `qwen3.5-tuned` 9.7B (`num_ctx 8192`) | — | **7,921 MiB** | **271 MiB** |

The 9.7B lands at ~7,920 MiB **under both desktop conditions** (7,921 quiet; 7,883–7,939 busy),
i.e. Ollama sizes its allocation to whatever is free rather than taking a fixed amount. Margin
is 250–270 MiB either way: **97 % full**. `ollama ps` still reports `100% GPU`.

The 4B has a **fixed** 5,515 MiB footprint, so what varies is the free space:
**~2.2 GB free with an idle desktop, ~1.4 GB with a busy one.**

### The spill is intermittent, which is what makes it dangerous

At rest the 9.7B is well behaved and reproducible: **six consecutive long generations all landed
at 69–72 tok/s**. But during one benchmark sweep the same model on the same prompt **collapsed to
19–21 tok/s**, with prompt processing falling from ~800 to ~133 tok/s and TTFT rising from 0.20 s
to 0.66 s.

> ⚠️ **Quote ~70 tok/s as the 9.7B's speed.** The collapse is an intermittent failure under
> desktop VRAM contention, not a steady-state number. It did not reproduce on demand — a
> deliberate attempt to trigger it (six long runs while sampling `nvidia-smi` every second) held
> 69–72 tok/s the whole way. That irreproducibility *is* the finding: it is fast every time you
> test it and slow the one time someone else needs it.

## 3. Thinking must be disabled — reproduced

Claim under test, from `CLAUDE.md`: with the big system prompt plus RAG chunks inside
`num_ctx 4096`, the reasoning trace blows the token budget → **~100 s latency and empty or
truncated answers**.

Reproduced against `qwen3.5-4b-tuned` with the context deliberately filled to `num_ctx` (4,096
prompt tokens: system prompt + synthetic manual chunks sized to the real RAG range of
1,547–2,284), `seed 42`:

| `think` | wall | output tokens | reasoning | answer returned |
|---|---|---|---|---|
| `false` | **3.7 s** / 6.7 s | 114 | 0 chars | 420 chars, clean |
| `false` | 3.7 s | 114 | 0 chars | 420 chars, clean |
| `true` | **92.9 s** | 8,190 | 29,254 chars | **0 chars — empty** |
| `true` | 51.0 s | 4,561 | 16,993 chars | 464 chars |

**Confirmed.** 92.9 s is the "roughly 100 seconds", and the empty answer reproduced exactly.
The failure is the reasoning trace consuming the entire output budget before the answer starts.

Cost of thinking on an *unconstrained* short prompt, for contrast (no context pressure):

| model | `think: false` | `think: true` |
|---|---|---|
| `qwen3.5-4b-tuned` | 10.1–14.1 s, 990 tok | 26.9–29.9 s, 2,615 tok (5,527 chars reasoning) |
| `qwen3.5-tuned` 9.7B | 10.5–15.1 s, 739 tok | 10.6–14.0 s, 753 tok (487 chars reasoning) |

So thinking is only catastrophic **when the context is full**. That is why the fix is mandatory
for the RAG path specifically. `/no_think` in the prompt does not work on this build
(verified 2026-06-11: still emitted 479 reasoning tokens); `think: false` must be a param on the
Open WebUI `Family1` model, because `/api/chat/completions` does not forward a request-level
`think` field.

## 4. End-to-end through Open WebUI — what the family actually feels

`POST /api/chat/completions` against `ollama-family1:latest` (display name `Family1`, house
manual attached as a knowledge collection). Prompt sizes after retrieval: 1,547–2,284 tokens;
answers 75–601 tokens.

| | |
|---|---|
| fastest | **2.3 s** |
| typical | **3–6 s** |
| slowest (first request, cold cache) | 8.4 s |

### Cold start no longer costs two minutes

`CLAUDE.md` records a cold start (model load + first RAG) of **100–134 s**, which is why the
bot's HTTP timeout is 180 s. **That no longer reproduces.** Measured with the Ollama model
unloaded *and* the `open-webui` container restarted to clear its caches:

| request | wall | prompt tokens | answer |
|---|---|---|---|
| #0 — genuinely cold | **9.8 s** | 1,928 | 1,801 chars |
| #1 | 6.2 s | 1,869 | 1,833 chars |
| #2 | 6.2 s | 1,928 | 1,842 chars |
| #3 | 5.4 s | 1,928 | 1,472 chars |

The 100–134 s figure is **historical** — it belongs to an earlier state of the stack, not to the
current one. Keeping the 180 s timeout is still the right call (a timeout you never reach costs
nothing), but the two-minute cold start should not be presented as current behaviour.

## 5. Model inventory at time of measurement

| model | params | quant | size |
|---|---|---|---|
| `qwen3.5-4b-tuned:latest` | 4.7B | Q4_K_M | 3.4 GB | ← production engine |
| `qwen3.5:4b` | 4.7B | Q4_K_M | 3.4 GB | ← base for the above |
| `qwen3.5-tuned:latest` | 9.7B | Q4_K_M | 6.6 GB | ← the original oversized engine |
| `qwen3.5:latest` | 9.7B | Q4_K_M | 6.6 GB |
| `llama3.2:latest` | 3.2B | Q4_K_M | 2.0 GB |
| `family1:latest` | 6.7B | Q4_0 | 3.8 GB | ← the original Llama-based attempt |
| `llama2-uncensored:latest` | 6.7B | Q4_0 | 3.8 GB |

`llama3.1` is **not** installed. Blog part 1 mentions it only as the historically accurate 2024
choice.

## Reproducing

```bash
python3 bench/bench_generation.py     # section 1 and 2
python3 bench/bench_thinking.py       # section 3
python3 bench/bench_endtoend.py       # section 4 (needs OPENWEBUI_API_KEY in .env)
```

`bench_endtoend.py` restarts the `open-webui` container to measure a genuine cold start.
It comes back on its own (`restart: always`), but do not run it while somebody is asking the
assistant something.
