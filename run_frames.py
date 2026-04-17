"""
FRAMES benchmark runner for Bielik (or any OpenAI-compatible model).

Two modes:
  - naive   : ask the question with no context
  - oracle  : fetch the linked Wikipedia articles and paste them as context

Judge: a separate LLM (default: gpt-4.1) scores the prediction against the
gold answer using the prompt from the FRAMES paper appendix.

Resumable: every completed row is appended to JSONL; rerunning skips done rows.

Usage:
    # Start Bielik via vLLM first, e.g.:
    #   vllm serve speakleash/Bielik-11B-v3.0-Instruct --port 8000
    #
    # Then:
    python run_frames.py --mode naive --model bielik \\
        --base-url http://localhost:8000/v1 --out results/bielik_naive.jsonl

    python run_frames.py --mode oracle --model bielik \\
        --base-url http://localhost:8000/v1 --out results/bielik_oracle.jsonl

    # Judge pass (uses OPENAI_API_KEY for gpt-4.1 by default):
    python run_frames.py --judge results/bielik_naive.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import requests
from datasets import load_dataset
from openai import OpenAI


# ---------- Prompts (from FRAMES paper appendix) ----------

NAIVE_PROMPT = """Answer the following question. Give only the final answer, concisely.

Question: {question}

Answer:"""

ORACLE_PROMPT = """Here are relevant Wikipedia articles. Use them to answer the question.

{context}

Question: {question}

Give only the final answer, concisely.

Answer:"""

# Judge prompt — reproduced from the paper's appendix; same as optillm uses.
JUDGE_PROMPT = """===Task===
I need your help in evaluating an answer provided by an LLM against a ground
truth answer. Your task is to determine if the ground truth answer is present
in the LLM's response. Please analyze the provided data and make a decision.

===Instructions===
1. Carefully compare the "Predicted Answer" with the "Ground Truth Answer".
2. Consider the substance of the answers - look for equivalent information or
   correct answers. Do not focus on exact wording unless the exact wording is
   crucial to the meaning.
3. Your final decision should be based on whether the meaning and the vital
   facts of the "Ground Truth Answer" are present in the "Predicted Answer".

===Input Data===
- Question: {question}
- Predicted Answer: {predicted}
- Ground Truth Answer: {gold}

===Output Format===
Provide your final evaluation in the following format:
"Explanation:" (How you made the decision?)
"Decision:" ("TRUE" or "FALSE")

Please proceed with the evaluation."""


# ---------- Wikipedia fetching ----------

WIKI_CACHE = Path("wiki_cache")
WIKI_CACHE.mkdir(exist_ok=True)


def fetch_wiki_plain(url: str) -> str:
    """Fetch plain-text content of a Wikipedia article. Cached on disk."""
    # Normalize — handle en.m.wikipedia, anchors, %-encoding variants.
    m = re.match(r"https?://en(?:\.m)?\.wikipedia\.org/wiki/([^#?]+)", url)
    if not m:
        return ""
    title = m.group(1)
    cache_file = WIKI_CACHE / f"{re.sub(r'[^A-Za-z0-9._-]', '_', title)}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "format": "json",
        "titles": requests.utils.unquote(title),
    }
    try:
        r = requests.get(api, params=params, timeout=30,
                         headers={"User-Agent": "frames-bielik/0.1"})
        r.raise_for_status()
        pages = r.json()["query"]["pages"]
        text = next(iter(pages.values())).get("extract", "") or ""
    except Exception as e:
        print(f"  [warn] wiki fetch failed for {url}: {e}", file=sys.stderr)
        text = ""
    cache_file.write_text(text, encoding="utf-8")
    return text


def build_oracle_context(row: dict, budget_chars: int = 60_000) -> str:
    """Fetch all linked Wiki articles and concatenate up to a char budget."""
    links = [row[f"wikipedia_link_{i}"] for i in range(1, 12)
             if row.get(f"wikipedia_link_{i}")]
    chunks, used = [], 0
    per_article = max(budget_chars // max(len(links), 1), 2000)
    for url in links:
        txt = fetch_wiki_plain(url)
        if not txt:
            continue
        snippet = txt[:per_article]
        chunks.append(f"--- {url} ---\n{snippet}")
        used += len(snippet)
        if used >= budget_chars:
            break
    return "\n\n".join(chunks)


# ---------- Model calls ----------

def call_chat(client: OpenAI, model: str, prompt: str,
              system: str | None = None, max_tokens: int = 512) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                temperature=0.0, max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            wait = 2 ** attempt
            print(f"  [retry {attempt+1}] {e} — sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
    return ""


# ---------- Runner ----------

def load_done(path: Path) -> set[int]:
    if not path.exists():
        return set()
    done = set()
    with path.open() as f:
        for line in f:
            try:
                done.add(json.loads(line)["idx"])
            except Exception:
                pass
    return done


def run_predictions(args) -> None:
    ds = load_dataset("google/frames-benchmark", split="test")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path)
    print(f"Already done: {len(done)} / {len(ds)}")

    client = OpenAI(base_url=args.base_url, api_key=args.api_key or "EMPTY")
    system = ("Jesteś pomocnym asystentem Bielik."
              if args.model.lower().startswith("bielik") else None)

    def process(i: int) -> dict:
        row = ds[i]
        q = row["Prompt"]
        if args.mode == "naive":
            prompt = NAIVE_PROMPT.format(question=q)
        else:
            ctx = build_oracle_context(row, budget_chars=args.context_chars)
            prompt = ORACLE_PROMPT.format(context=ctx, question=q)
        pred = call_chat(client, args.model, prompt, system=system)
        return {"idx": i, "question": q, "gold": row["Answer"],
                "prediction": pred, "reasoning_types": row.get("reasoning_types", "")}

    todo = [i for i in range(len(ds)) if i not in done]
    if args.limit:
        todo = todo[:args.limit]

    with out_path.open("a") as fout, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, i): i for i in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                rec = fut.result()
            except Exception as e:
                print(f"  [error] idx={futs[fut]}: {e}", file=sys.stderr)
                continue
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            if n % 10 == 0:
                print(f"  {n}/{len(todo)}")
    print("Predictions done.")


# ---------- Judge ----------

def run_judge(args) -> None:
    in_path = Path(args.judge)
    scored_path = in_path.with_suffix(".scored.jsonl")
    done = load_done(scored_path)

    judge_client = OpenAI(
        base_url=args.judge_base_url,
        api_key=args.judge_api_key or os.environ.get("OPENAI_API_KEY", ""),
    )

    rows = [json.loads(l) for l in in_path.open()]
    todo = [r for r in rows if r["idx"] not in done]
    print(f"Judging {len(todo)} / {len(rows)} (judge={args.judge_model})")

    def judge_one(rec: dict) -> dict:
        msg = JUDGE_PROMPT.format(
            question=rec["question"], predicted=rec["prediction"], gold=rec["gold"]
        )
        out = call_chat(judge_client, args.judge_model, msg, max_tokens=400)
        decision = "TRUE" if re.search(r'Decision[:\s]+"?TRUE"?', out, re.I) else "FALSE"
        return {**rec, "judge_raw": out, "correct": decision == "TRUE"}

    with scored_path.open("a") as fout, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(judge_one, r) for r in todo]
        for n, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            if n % 25 == 0:
                print(f"  judged {n}/{len(todo)}")

    # Aggregate
    all_rows = [json.loads(l) for l in scored_path.open()]
    acc = sum(r["correct"] for r in all_rows) / len(all_rows)
    print(f"\nAccuracy: {acc:.4f}  ({sum(r['correct'] for r in all_rows)}/{len(all_rows)})")

    # Break down by reasoning type
    buckets: dict[str, list[bool]] = {}
    for r in all_rows:
        for t in (r.get("reasoning_types") or "Unlabeled").split("|"):
            buckets.setdefault(t.strip(), []).append(r["correct"])
    print("\nPer reasoning type:")
    for t, vals in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"  {t:35s} {sum(vals)/len(vals):.3f}  (n={len(vals)})")


# ---------- CLI ----------

def main():
    p = argparse.ArgumentParser(
        description="FRAMES benchmark runner — test any OpenAI-compatible model "
                    "on 824 multi-hop questions from Google's FRAMES dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Naive run (no context, measures raw knowledge)
  python run_frames.py --mode naive --model bielik --out results/naive.jsonl

  # Oracle run (full Wiki articles as context)
  python run_frames.py --mode oracle --model bielik --context-chars 80000

  # Judge pass (score predictions with gpt-4.1)
  python run_frames.py --judge results/naive.jsonl --judge-model gpt-4.1
""")

    g_pred = p.add_argument_group("prediction mode")
    g_pred.add_argument("--mode", choices=["naive", "oracle"], default="naive",
                        help="naive = no context, oracle = full Wiki articles (default: naive)")
    g_pred.add_argument("--model", default="bielik",
                        help="model name as served by vLLM/Ollama (default: bielik)")
    g_pred.add_argument("--base-url", default="http://localhost:8000/v1",
                        help="OpenAI-compatible API base URL (default: http://localhost:8000/v1)")
    g_pred.add_argument("--api-key", default="EMPTY",
                        help="API key for the model server (default: EMPTY)")
    g_pred.add_argument("--out", default="results/run.jsonl",
                        help="output JSONL path (default: results/run.jsonl)")
    g_pred.add_argument("--workers", type=int, default=4,
                        help="parallel workers (default: 4)")
    g_pred.add_argument("--limit", type=int, default=0,
                        help="run only first N questions, 0 = all (default: 0)")
    g_pred.add_argument("--context-chars", type=int, default=60_000,
                        help="max context chars per question in oracle mode (default: 60000)")

    g_judge = p.add_argument_group("judge mode")
    g_judge.add_argument("--judge",
                         help="path to predictions JSONL to score (enables judge mode)")
    g_judge.add_argument("--judge-model", default="gpt-4.1",
                         help="LLM judge model (default: gpt-4.1)")
    g_judge.add_argument("--judge-base-url", default="https://api.openai.com/v1",
                         help="judge API base URL (default: https://api.openai.com/v1)")
    g_judge.add_argument("--judge-api-key", default="",
                         help="judge API key (default: OPENAI_API_KEY env var)")
    args = p.parse_args()

    if args.judge:
        run_judge(args)
    else:
        run_predictions(args)


if __name__ == "__main__":
    main()
