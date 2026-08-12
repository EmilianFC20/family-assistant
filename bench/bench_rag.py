#!/usr/bin/env python3
"""Section 6 of BENCHMARKS.md — retrieval quality.

Scores retrieval alone: for each question it asks Open WebUI's
/api/v1/retrieval/query/collection endpoint for the top-k chunks and checks whether the
gold string is present verbatim in what came back. **No LLM is involved.** A hit means the
answer was on the model's desk; whether the model then reads it correctly is a different
question, deliberately not measured here — mixing the two makes a retrieval regression
indistinguishable from a generation one.

The question set lives OUTSIDE this repo because the gold strings are real family
passwords. Point RAG_GOLDSET at it (default ~/Emster/rag_goldset.json):

    python3 bench/bench_rag.py --collection <id> --label "production" --k 3 5 8
    python3 bench/bench_rag.py --collection <id> --label "clean" --k 3 5 8 --markdown

Nothing this script prints contains a gold string: results are reported as question id +
hit/miss, so the output is safe to paste into BENCHMARKS.md or a blog post.

A miss is only meaningful if the fact is really in the corpus, so pass --source with the
manual the collection was built from and every gold string is checked against it up front.
Do not try to establish that with a wide-k retrieval sweep instead: on the bloated manual
(959 chunks, 95 % of them base64 image noise) even k=40 fails to surface facts that are
demonstrably in the file, which reads as "missing from the corpus" when it is nothing of
the kind. Grep the source; only the ranking is in question here.
"""
import argparse
import json
import os
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_GOLDSET = pathlib.Path.home() / "Emster" / "rag_goldset.json"


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
    for key in ("OPENWEBUI_URL", "OPENWEBUI_API_KEY"):
        if not env.get(key):
            sys.exit(f"{key} is missing from .env")
    return env


def load_goldset():
    path = pathlib.Path(os.environ.get("RAG_GOLDSET", DEFAULT_GOLDSET))
    if not path.exists():
        sys.exit(f"No gold set at {path}. Set RAG_GOLDSET to its location.\n"
                 "It is kept out of the repo on purpose — it contains real passwords.")
    if path.is_relative_to(ROOT):
        sys.exit(f"Refusing to read a gold set from inside the repo ({path}).\n"
                 "It contains real passwords and must live outside version control.")
    return json.loads(path.read_text())["questions"]


def query(env, collection, text, k):
    """Top-k chunks for one query. Returns the chunk texts."""
    r = requests.post(
        f"{env['OPENWEBUI_URL'].rstrip('/')}/api/v1/retrieval/query/collection",
        headers={"Authorization": f"Bearer {env['OPENWEBUI_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"collection_names": [collection], "query": text, "k": k},
        timeout=120)
    r.raise_for_status()
    docs = r.json().get("documents") or [[]]
    return docs[0] if docs else []


def hit(chunks, gold_alternatives):
    """True if any accepted gold string appears verbatim in any retrieved chunk."""
    blob = "\n".join(chunks).lower()
    return any(g.lower() in blob for g in gold_alternatives)


def check_source(path, questions):
    """Every gold string must exist in the manual, or the gold set itself is wrong."""
    text = pathlib.Path(path).read_text(errors="ignore").lower()
    absent = [q["id"] for q in questions
              if not any(g.lower() in text for g in q["gold"])]
    if absent:
        sys.exit(f"These gold strings are not in {path}: {', '.join(absent)}\n"
                 "Fix the gold set (or point --source at the right manual) before scoring; "
                 "otherwise their misses measure nothing.")
    print(f"source check: all {len(questions)} facts present in {pathlib.Path(path).name}\n")


def run(env, collection, k, questions):
    results = []
    for q in questions:
        chunks = query(env, collection, q["question"], k)
        status = "hit" if hit(chunks, q["gold"]) else "miss"
        results.append((q["id"], q.get("topic", ""), status))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, help="Open WebUI knowledge collection id")
    ap.add_argument("--label", default="", help="name for this config in the output")
    ap.add_argument("--k", type=int, nargs="+", default=[3, 5, 8])
    ap.add_argument("--source", help="manual the collection was built from; gold strings "
                                     "are checked against it before scoring")
    ap.add_argument("--markdown", action="store_true", help="also print a markdown table")
    args = ap.parse_args()

    env = load_env()
    questions = load_goldset()
    label = args.label or args.collection[:8]
    print(f"{label}  collection={args.collection}  {len(questions)} questions\n")
    if args.source:
        check_source(args.source, questions)

    scored = {}
    for k in args.k:
        results = run(env, args.collection, k, questions)
        hits = sum(1 for _, _, s in results if s == "hit")
        scored[k] = (hits, results)

        print(f"k={k}:  {hits}/{len(questions)}")
        for qid, topic, status in results:
            if status != "hit":
                print(f"     MISS  {qid:26s} ({topic})")
        print()

    if args.markdown:
        print(f"| config | " + " | ".join(f"k={k}" for k in args.k) + " |")
        print("|---|" + "---|" * len(args.k))
        cells = " | ".join(f"**{scored[k][0]}/{len(questions)}**" for k in args.k)
        print(f"| {label} | {cells} |")


if __name__ == "__main__":
    main()
