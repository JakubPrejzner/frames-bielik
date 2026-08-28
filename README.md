# FRAMES benchmark - universal runner

A tool for testing **any model** (Bielik, Qwen, Llama, GPT, Claude — anything with an OpenAI-compatible API) on Google's [FRAMES](https://arxiv.org/abs/2409.12941) benchmark (824 multi-hop questions grounded in Wikipedia).

Built in response to the "Identifying the FRAMES benchmark" thread on the [SpeakLeash](https://speakleash.org/) Discord.

## What you get

- **Evaluation script** — `naive` mode (no context) + `oracle` mode (full Wiki articles)
- **Resumable** - crash → restart → continues from where it left off
- **LLM-as-judge** - judge prompt taken 1:1 from Google's paper appendix
- **Wikipedia cache** with rate limiting (to avoid getting banned by the Wiki API)
- **JSONL output** - easy to analyze, one JSON object per line

## Quick start - testing Bielik

### Requirements

- 1× GPU with 24GB+ VRAM (H100, A100, RTX 4090)
- Python 3.10+
- OpenAI API key (for the judge) — can be swapped for any model

### Setup (5 min)

```bash
git clone https://github.com/JakubPrejzner/frames-bielik.git
cd frames-bielik

pip install -r requirements.txt

# Serve the model via vLLM (requires a GPU)
pip install vllm
vllm serve speakleash/Bielik-11B-v3.0-Instruct \
    --port 8000 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.9
```

### Smoke test (10 questions, ~5 seconds)

```bash
python run_frames.py \
    --mode naive \
    --model "speakleash/Bielik-11B-v3.0-Instruct" \
    --base-url http://localhost:8000/v1 \
    --limit 10 \
    --out results/smoke.jsonl
```

### Full run — naive

```bash
python run_frames.py \
    --mode naive \
    --model "speakleash/Bielik-11B-v3.0-Instruct" \
    --base-url http://localhost:8000/v1 \
    --workers 8 \
    --out results/bielik_v3_naive.jsonl
```

### Full run — oracle

```bash
python run_frames.py \
    --mode oracle \
    --model "speakleash/Bielik-11B-v3.0-Instruct" \
    --base-url http://localhost:8000/v1 \
    --context-chars 80000 \
    --workers 4 \
    --out results/bielik_v3_oracle.jsonl
```

> **Note**: the first oracle run downloads ~2500 articles from Wikipedia into `wiki_cache/`. At a rate limit of 1 req/s this takes ~30 min. Subsequent runs use the cache.

### Judge scoring

```bash
export OPENAI_API_KEY=sk-...

python run_frames.py \
    --judge results/bielik_v3_naive.jsonl \
    --judge-model gpt-4.1 \
    --workers 16

python run_frames.py \
    --judge results/bielik_v3_oracle.jsonl \
    --judge-model gpt-4.1 \
    --workers 16
```

The script prints overall accuracy plus a breakdown by reasoning type.

## Running against a DIFFERENT model

Change `--model` and `--base-url`. Examples:

```bash
# Qwen via vLLM
vllm serve Qwen/Qwen2.5-14B-Instruct --port 8000
python run_frames.py --mode naive \
    --model "Qwen/Qwen2.5-14B-Instruct" \
    --base-url http://localhost:8000/v1 \
    --out results/qwen_naive.jsonl

# Ollama (runs on CPU)
ollama pull llama3.1:8b
python run_frames.py --mode naive \
    --model "llama3.1:8b" \
    --base-url http://localhost:11434/v1 \
    --out results/llama_naive.jsonl

# OpenAI API (no local GPU needed)
python run_frames.py --mode naive \
    --model "gpt-4.1-mini" \
    --base-url https://api.openai.com/v1 \
    --api-key $OPENAI_API_KEY \
    --out results/gpt4mini_naive.jsonl
```

## Evaluation modes

### naive (no context)

Measures the model's parametric knowledge. The question goes to the model with no context at all.

- Fast: ~30s for 824 questions on an H100
- Paper reference: Gemini Pro 1.5 = 40.8%

### oracle (full Wiki articles in context)

Upper bound for reading comprehension. The model gets the full text of the Wikipedia articles provided in the dataset. **This is NOT a RAG test with retrieval** — the model gets all documents at once, it doesn't have to search for them.

- Slower: ~10-15 min on an H100
- Paper reference: Gemini Pro 1.5 = 72.9%
- `--context-chars` controls how many characters of context the model gets (default 60k)

## Output files

Predictions (`results/*.jsonl`):
```json
{"idx": 0, "question": "...", "gold": "...", "prediction": "...", "reasoning_types": "Multiple constraints"}
```

After judge scoring (`results/*.scored.jsonl`):
```json
{"idx": 0, "question": "...", "gold": "...", "prediction": "...", "reasoning_types": "...", "judge_raw": "Explanation: ... Decision: TRUE", "correct": true}
```

## What this tool does NOT do (yet)

- No BM25 / dense retrieval — on the roadmap
- No agentic multi-step retrieval — separate project
- Does not translate questions into Polish (original English dataset only)

If you want these features — PRs welcome.

## My results (Bielik-11B-v3.0-Instruct)

| Mode | Accuracy | n_correct / n_total |
| --- | --- | --- |
| Naive | 12.38% | 102 / 824 |
| Oracle | 52.31% | 431 / 824 |

Judge: `gpt-4.1`, temperature 0.0. Full report with error analysis: [REPORT.md](REPORT.md)

## References

- FRAMES paper: https://arxiv.org/abs/2409.12941
- Dataset: https://huggingface.co/datasets/google/frames-benchmark
- Script inspiration: [codelion/optillm](https://github.com/codelion/optillm/blob/main/scripts/eval_frames_benchmark.py)

## License

MIT

## Acknowledgments

- Google for the FRAMES dataset and judge prompt
- [SpeakLeash](https://speakleash.org/) for Bielik and the Discord thread community
- [codelion/optillm](https://github.com/codelion/optillm) — where the original judge prompt inspiration came from
