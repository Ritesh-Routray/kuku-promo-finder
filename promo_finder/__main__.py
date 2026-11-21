"""CLI: python -m promo_finder --input <scripts folder> --out <run folder> [--generator MODEL] [--judge MODEL]"""
from __future__ import annotations

import argparse
from datetime import datetime

from .config import load_config
from .pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser(description="Find and rank promo clips in microdrama screenplays.")
    ap.add_argument("--input", required=True, help="folder of episode .txt screenplays")
    ap.add_argument("--out", default=None, help="output folder (default outputs/run_<timestamp>)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--generator", default=None, help="override generator model, e.g. groq/llama-3.3-70b-versatile")
    ap.add_argument("--judge", default=None, help="override judge model")
    ap.add_argument("--offline", action="store_true", help="no LLM: heuristic generator + judge")
    ap.add_argument("--show", default=None)
    ap.add_argument("--limit", type=int, default=None, help="only the first N episodes")
    a = ap.parse_args()

    models = {}
    if a.offline:
        models = {"generator": "heuristic", "judge": "heuristic"}
    if a.generator:
        models["generator"] = a.generator
    if a.judge:
        models["judge"] = a.judge
    cfg = load_config(a.config, {"models": models} if models else None)
    out = a.out or f"outputs/run_{datetime.now():%Y%m%d_%H%M%S}"
    log = run(a.input, out, cfg, show=a.show, episodes_limit=a.limit)
    print(f"\nWrote {out}  |  ranked {log['ranked']}  |  LLM calls {log['llm']['live_calls']}  |  errors {len(log['errors'])}")


if __name__ == "__main__":
    main()
