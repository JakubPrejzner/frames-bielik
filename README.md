# FRAMES benchmark - uniwersalny runner

Narzędzie do testowania **dowolnego modelu** (Bielik, Qwen, Llama, GPT, Claude — cokolwiek z OpenAI-compatible API) na benchmarku [FRAMES](https://arxiv.org/abs/2409.12941) od Google (824 pytania multi-hop z Wikipedii).

Powstało jako odpowiedź na wątek "Rozpoznać benchmark FRAMES" na Discordzie [SpeakLeash](https://speakleash.org/).

## Co dostajesz

- **Skrypt ewaluacyjny** — tryb `naive` (bez kontekstu) + `oracle` (pełne artykuły Wiki)
- **Resumable** - crash → restart → kontynuacja od miejsca przerwania
- **LLM-as-judge** - prompt sędziego 1:1 z appendixu papera Google
- **Cache Wikipedii** z rate limitingiem (żeby nie dostać bana od Wiki API)
- **Output w JSONL** - łatwy do analizy, po jednym JSON per wiersz

## Szybki start - testowanie Bielika

### Wymagania

- 1× GPU z 24GB+ VRAM (H100, A100, RTX 4090)
- Python 3.10+
- Klucz OpenAI API (do sędziego) — można zamienić na dowolny model

### Setup (5 min)

```bash
git clone https://github.com/JakubPrejzner/frames-bielik.git
cd frames-bielik

pip install -r requirements.txt

# Serwowanie modelu przez vLLM (wymaga GPU)
pip install vllm
vllm serve speakleash/Bielik-11B-v3.0-Instruct \
    --port 8000 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.9
```

### Smoke test (10 pytań, ~5 sekund)

```bash
python run_frames.py \
    --mode naive \
    --model "speakleash/Bielik-11B-v3.0-Instruct" \
    --base-url http://localhost:8000/v1 \
    --limit 10 \
    --out results/smoke.jsonl
```

### Pełny run — naive

```bash
python run_frames.py \
    --mode naive \
    --model "speakleash/Bielik-11B-v3.0-Instruct" \
    --base-url http://localhost:8000/v1 \
    --workers 8 \
    --out results/bielik_v3_naive.jsonl
```

### Pełny run — oracle

```bash
python run_frames.py \
    --mode oracle \
    --model "speakleash/Bielik-11B-v3.0-Instruct" \
    --base-url http://localhost:8000/v1 \
    --context-chars 80000 \
    --workers 4 \
    --out results/bielik_v3_oracle.jsonl
```

> **Uwaga**: pierwszy run oracle pobiera ~2500 artykułów z Wikipedii do `wiki_cache/`. Przy rate limicie 1 req/s trwa to ~30 min. Kolejne uruchomienia korzystają z cache.

### Ocena judge

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

Skrypt wypisze accuracy globalną + breakdown per typ rozumowania.

## Uruchomienie dla INNEGO modelu

Zmień `--model` i `--base-url`. Przykłady:

```bash
# Qwen przez vLLM
vllm serve Qwen/Qwen2.5-14B-Instruct --port 8000
python run_frames.py --mode naive \
    --model "Qwen/Qwen2.5-14B-Instruct" \
    --base-url http://localhost:8000/v1 \
    --out results/qwen_naive.jsonl

# Ollama (działa na CPU)
ollama pull llama3.1:8b
python run_frames.py --mode naive \
    --model "llama3.1:8b" \
    --base-url http://localhost:11434/v1 \
    --out results/llama_naive.jsonl

# OpenAI API (bez lokalnego GPU)
python run_frames.py --mode naive \
    --model "gpt-4.1-mini" \
    --base-url https://api.openai.com/v1 \
    --api-key $OPENAI_API_KEY \
    --out results/gpt4mini_naive.jsonl
```

## Tryby ewaluacji

### naive (bez kontekstu)

Mierzy zaszytą wiedzę modelu. Pytanie idzie do modelu bez żadnego kontekstu.

- Szybkie: ~30s dla 824 pytań na H100
- Referencja z papera: Gemini Pro 1.5 = 40.8%

### oracle (pełne artykuły Wiki w kontekście)

Upper bound reading comprehension. Model dostaje pełne treści artykułów Wikipedii podanych w datasecie. **NIE jest to test RAG z retrieval-em** — model dostaje wszystkie dokumenty na raz, nie musi ich wyszukiwać.

- Wolniejsze: ~10-15 min na H100
- Referencja z papera: Gemini Pro 1.5 = 72.9%
- `--context-chars` kontroluje ile znaków kontekstu model dostaje (domyślnie 60k)

## Pliki wyjściowe

Predykcje (`results/*.jsonl`):
```json
{"idx": 0, "question": "...", "gold": "...", "prediction": "...", "reasoning_types": "Multiple constraints"}
```

Po ocenie sędzią (`results/*.scored.jsonl`):
```json
{"idx": 0, "question": "...", "gold": "...", "prediction": "...", "reasoning_types": "...", "judge_raw": "Explanation: ... Decision: TRUE", "correct": true}
```

## Czego to narzędzie NIE robi (jeszcze)

- Nie ma BM25 / dense retrieval — to jest na roadmapie
- Nie ma agentic multi-step retrieval — to osobny projekt
- Nie tłumaczy pytań na polski (tylko oryginalny angielski dataset)

Jeśli chcesz te funkcjonalności — PR mile widziane.

## Moje wyniki (Bielik-11B-v3.0-Instruct)

| Tryb | Accuracy | n_correct / n_total |
| --- | --- | --- |
| Naive | 12.38% | 102 / 824 |
| Oracle | 52.31% | 431 / 824 |

Sędzia: `gpt-4.1`, temperature 0.0. Pełny raport z analizą błędów: [REPORT.md](REPORT.md)

## Referencje

- Paper FRAMES: https://arxiv.org/abs/2409.12941
- Dataset: https://huggingface.co/datasets/google/frames-benchmark
- Inspiracja skryptu: [codelion/optillm](https://github.com/codelion/optillm/blob/main/scripts/eval_frames_benchmark.py)

## Licencja

MIT

## Podziękowania

- Google za dataset FRAMES i prompt sędziego
- [SpeakLeash](https://speakleash.org/) za Bielika i community wątku na Discordzie
- [codelion/optillm](https://github.com/codelion/optillm) — skąd wzięliśmy pierwotną inspirację promptu sędziego
