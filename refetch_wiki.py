"""
Re-fetch empty Wikipedia cache files with proper rate limiting and retry logic.
Iterates over the FRAMES dataset to get correct URLs, not cache filenames.

Usage:
    python refetch_wiki.py [--workers 4] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from datasets import load_dataset

WIKI_CACHE = Path("wiki_cache")
USER_AGENT = "frames-bielik-eval/0.2 (https://github.com/JakubPrejzner; rd4drop@gmail.com)"

# Global rate limiter: max 1 request per second across all threads
_rate_lock = threading.Lock()
_last_request_time = 0.0


def url_to_cache_path(url: str) -> tuple[Path, str] | None:
    """Extract title from URL and compute cache path — same logic as run_frames.py."""
    m = re.match(r"https?://en(?:\.m)?\.wikipedia\.org/wiki/([^#?]+)", url)
    if not m:
        return None
    title = m.group(1)
    cache_file = WIKI_CACHE / f"{re.sub(r'[^A-Za-z0-9._-]', '_', title)}.txt"
    decoded_title = requests.utils.unquote(title)
    return cache_file, decoded_title


def rate_limited_get(url: str, params: dict, timeout: int = 30) -> requests.Response:
    """GET with global 1 req/s rate limit."""
    global _last_request_time
    with _rate_lock:
        now = time.monotonic()
        wait = max(0.0, 1.0 - (now - _last_request_time))
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()
    return requests.get(url, params=params, timeout=timeout,
                        headers={"User-Agent": USER_AGENT})


def fetch_one(url: str, cache_file: Path, decoded_title: str) -> tuple[str, bool, str]:
    """Fetch a single article. Returns (url, success, detail)."""
    api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "format": "json",
        "titles": decoded_title,
    }

    retry_delays = [30, 60, 120]

    for attempt in range(len(retry_delays) + 1):
        try:
            r = rate_limited_get(api, params)
            if r.status_code == 429:
                if attempt < len(retry_delays):
                    delay = retry_delays[attempt]
                    print(f"  [429] {decoded_title} — retrying in {delay}s "
                          f"(attempt {attempt+1}/{len(retry_delays)})",
                          file=sys.stderr)
                    time.sleep(delay)
                    continue
                else:
                    print(f"  [GIVE UP] {decoded_title} — 429 after all retries",
                          file=sys.stderr)
                    return (url, False, "429 after all retries")

            r.raise_for_status()
            pages = r.json()["query"]["pages"]
            text = next(iter(pages.values())).get("extract", "") or ""

            if text:
                cache_file.write_text(text, encoding="utf-8")
                return (url, True, f"{len(text)} chars")
            else:
                return (url, False, "empty extract from API")

        except requests.exceptions.HTTPError as e:
            if "429" in str(e) and attempt < len(retry_delays):
                delay = retry_delays[attempt]
                print(f"  [429] {decoded_title} — retrying in {delay}s",
                      file=sys.stderr)
                time.sleep(delay)
                continue
            return (url, False, str(e))
        except Exception as e:
            return (url, False, str(e))

    return (url, False, "exhausted retries")


def collect_urls_from_dataset() -> set[str]:
    """Load FRAMES dataset and collect all unique Wikipedia URLs."""
    ds = load_dataset("google/frames-benchmark", split="test")
    urls = set()
    for row in ds:
        for i in range(1, 12):
            link = row.get(f"wikipedia_link_{i}")
            if link:
                urls.add(link)
    return urls


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dry-run", action="store_true",
                   help="Just count, don't fetch")
    args = p.parse_args()

    WIKI_CACHE.mkdir(exist_ok=True)

    print("Loading FRAMES dataset...")
    all_urls = collect_urls_from_dataset()
    print(f"Unique Wikipedia URLs in dataset: {len(all_urls)}")

    # Classify: which need fetching?
    to_fetch: list[tuple[str, Path, str]] = []  # (url, cache_path, decoded_title)
    already_ok = 0
    skipped_bad_url = 0

    for url in sorted(all_urls):
        result = url_to_cache_path(url)
        if result is None:
            skipped_bad_url += 1
            continue
        cache_file, decoded_title = result
        if cache_file.exists() and cache_file.stat().st_size > 0:
            already_ok += 1
        else:
            to_fetch.append((url, cache_file, decoded_title))

    print(f"Already cached (non-empty): {already_ok}")
    print(f"To re-fetch: {len(to_fetch)}")
    print(f"Skipped (non-en-wiki URL): {skipped_bad_url}")

    if args.dry_run or not to_fetch:
        return

    est_sec = len(to_fetch)
    print(f"\nStarting re-fetch with {args.workers} workers, 1 req/s global limit...")
    print(f"Estimated time: ~{est_sec}s ({est_sec // 60}m {est_sec % 60}s)\n")

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, url, cf, dt): url
                for url, cf, dt in to_fetch}
        for n, fut in enumerate(as_completed(futs), 1):
            url, success, detail = fut.result()
            if success:
                ok += 1
            else:
                fail += 1
            if n % 50 == 0 or n == len(to_fetch):
                print(f"  [{n}/{len(to_fetch)}] ok={ok} fail={fail}")

    # Final report
    total_cached = sum(1 for f in WIKI_CACHE.glob("*.txt")
                       if f.stat().st_size > 0)
    total_files = len(list(WIKI_CACHE.glob("*.txt")))
    print(f"\n=== DONE ===")
    print(f"Fetched OK:      {ok}")
    print(f"Failed:          {fail}")
    print(f"Total non-empty: {total_cached}/{total_files}")
    pct = total_cached / max(total_files, 1) * 100
    print(f"Cache coverage:  {pct:.1f}%")


if __name__ == "__main__":
    main()
