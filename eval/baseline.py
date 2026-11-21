"""Naive baseline for comparison: whole episode -> one LLM prompt -> promos with a self-rated score.
No heartbeat, no story memory, no rule snapping, no independent judges.

Usage: python eval/baseline.py --input <scripts folder> --out outputs/baseline [--model gemini/gemini-2.5-flash]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from promo_finder.config import load_config  # noqa: E402
from promo_finder.llm import LLM, LLMError  # noqa: E402
from promo_finder.parse import parse_folder, render_lines  # noqa: E402
from promo_finder.snap import _sec  # noqa: E402

PROMPT = """Here is episode {ep} of a short drama. Find up to 4 promo clips (20-60 seconds) for TikTok that open on a hook
and end on a cliffhanger. Give start and end timestamps and rate each 1-10.
Return JSON: {{"promos": [{{"title": "...", "start": "mm:ss.cc", "end": "mm:ss.cc", "hook_line": "...", "cliffhanger_line": "...", "why": "...", "rating": 7}}]}}

{script}"""


class BP(BaseModel):
    title: str
    start: str | float
    end: str | float
    hook_line: str = ""
    cliffhanger_line: str = ""
    why: str = ""
    rating: float = 5


class BOut(BaseModel):
    promos: list[BP]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="outputs/baseline")
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    cfg = load_config(overrides={"models": {"generator": a.model} if a.model else {}})
    llm = LLM(cfg)
    eps = parse_folder(a.input)[: a.limit]
    promos = []
    for e in eps:
        try:
            res = llm.json("generator", "You reply with JSON only.", PROMPT.format(ep=e.ep, script=render_lines(e.lines)),
                           schema=BOut, tag=f"baseline_ep{e.ep}")
        except LLMError as err:
            print("ep", e.ep, err)
            continue
        for i, p in enumerate(res["promos"]):
            s, t = _sec(p["start"]), _sec(p["end"])
            if t <= s:
                continue
            promos.append({"id": f"b{e.ep:03d}_{i + 1}", "ep": e.ep, "title": p["title"],
                           "segments": [{"ep": e.ep, "start": s, "end": t}], "duration": round(t - s, 2),
                           "hook_line": p["hook_line"], "hook_at": None, "cliffhanger_line": p["cliffhanger_line"],
                           "why": p["why"], "archetype": "other", "review_reasons": [], "flags": [],
                           "scores": {"score": p["rating"] * 10, "parts": {}},
                           "judge": {"cold_viewer": {"understood": False}}})
        print("ep", e.ep, "->", len(res["promos"]))
    promos.sort(key=lambda p: -p["scores"]["score"])
    for r, p in enumerate(promos, 1):
        p["rank"] = r
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "promos_ranked.json").write_text(json.dumps(promos[:25], indent=2, ensure_ascii=False), encoding="utf-8")
    in_range = sum(20 <= p["duration"] <= 60 for p in promos)
    (out / "run_log.json").write_text(json.dumps({"show": "baseline", "models": {"generator": cfg["models"]["generator"]},
                                                  "llm": llm.summary(), "total_promos": len(promos),
                                                  "within_20_60s": in_range}, indent=2), encoding="utf-8")
    print(f"{len(promos)} promos, {in_range} within 20-60s -> {out}")


if __name__ == "__main__":
    main()
