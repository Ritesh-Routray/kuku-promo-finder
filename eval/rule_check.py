"""Independent rule check for any run (tool or baseline), no gold set needed.

Re-finds each promo's hook and cliffhanger lines in the script and checks:
  length 20-60 s, hook starts within 3 s of the clip start, clip ends within 2 s of the cliffhanger line.

Usage: python eval/rule_check.py --input <scripts folder> --run outputs/run_A [--run outputs/baseline] [--top 25]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from promo_finder.parse import parse_folder  # noqa: E402
from promo_finder.snap import find_line  # noqa: E402


def check(promos: list[dict], eps: dict) -> dict:
    n = len(promos)
    c = {"length_20_60": 0, "hook_within_3s": 0, "ends_on_cliffhanger": 0, "all_three": 0}
    for p in promos:
        segs = [(s["start"], s["end"]) for s in p["segments"]]
        dur, s0, e1, ep = sum(b - a for a, b in segs), segs[0][0], segs[-1][1], eps[p["ep"]]
        ok_len = 20 <= dur <= 60
        h = find_line(ep.lines, p.get("hook_line", ""), s0 - 10, e1, allow_camera=True)  # visual hooks count
        ok_hook = h is not None and 0 <= h.start - s0 <= 3.01
        cl = find_line(ep.lines, p.get("cliffhanger_line", ""), s0, e1 + 8, allow_camera=True)
        ok_cliff = cl is not None and abs(cl.end - e1) <= 2.0
        c["length_20_60"] += ok_len
        c["hook_within_3s"] += ok_hook
        c["ends_on_cliffhanger"] += ok_cliff
        c["all_three"] += ok_len and ok_hook and ok_cliff
    return {"n": n, **{k: f"{v}/{n} ({100 * v / max(n, 1):.0f}%)" for k, v in c.items()}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    eps = {e.ep: e for e in parse_folder(Path(a.input))}
    for r in a.run:
        promos = sorted(json.loads((Path(r) / "promos_ranked.json").read_text(encoding="utf-8")), key=lambda p: p["rank"])
        print(r, json.dumps(check(promos[: a.top], eps)))


if __name__ == "__main__":
    main()
