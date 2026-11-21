"""Compare a run against hand-picked gold promos (and optionally a baseline run).

gold_promos.csv columns: id, ep, start, end   (times as mm:ss.cc or seconds; one row per segment;
multi-segment gold promos share an id). Write your own picks; the file is not committed.

Usage: python eval/evaluate.py --gold eval/gold_promos.csv --run outputs/run_X [--run outputs/run_baseline ...]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from promo_finder.parse import to_seconds  # noqa: E402
from promo_finder.snap import tiou  # noqa: E402


def _t(v: str) -> float:
    return to_seconds(v) if ":" in v else float(v)


def load_gold(path: Path) -> list[dict]:
    promos: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p = promos.setdefault(r["id"], {"id": r["id"], "segments": []})
            p["segments"].append({"ep": int(r["ep"]), "start": _t(r["start"]), "end": _t(r["end"])})
    return list(promos.values())


def evaluate(run: Path, gold: list[dict], thr: float) -> dict:
    ranked = json.loads((run / "promos_ranked.json").read_text(encoding="utf-8"))
    log = json.loads((run / "run_log.json").read_text(encoding="utf-8"))

    def hit(p):
        return max((tiou(p, g) for g in gold), default=0.0)

    best_iou = [hit(p) for p in ranked]
    res = {"run": run.name, "models": log.get("models"), "ranked": len(ranked)}
    for k in (5, 10, 25):
        top = best_iou[:k]
        res[f"precision@{k}"] = round(sum(x >= thr for x in top) / max(len(top), 1), 3)
    found = [max((tiou(g, p) for p in ranked), default=0.0) for g in gold]
    res["gold_recall"] = round(sum(x >= thr for x in found) / max(len(gold), 1), 3)
    res["mean_best_iou_gold"] = round(sum(found) / max(len(found), 1), 3)
    res["hook_in_3s"] = round(sum(1 for p in ranked if p["hook_at"] is not None and p["hook_at"] <= 3) / max(len(ranked), 1), 3)
    res["cold_viewer_understood"] = round(sum(p["judge"]["cold_viewer"]["understood"] for p in ranked) / max(len(ranked), 1), 3)
    res["needs_review"] = sum(bool(p["review_reasons"]) for p in ranked)
    res["episodes_covered_top10"] = len({p["ep"] for p in ranked[:10]})
    res["archetypes_top10"] = len({p["archetype"] for p in ranked[:10]})
    res["llm_calls"] = log.get("llm", {}).get("live_calls")
    res["seconds"] = log.get("seconds")
    res["rejected_by_rules"] = log.get("rejected")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--iou", type=float, default=0.3, help="tIoU threshold for a match")
    a = ap.parse_args()
    gold = load_gold(Path(a.gold))
    rows = [evaluate(Path(r), gold, a.iou) for r in a.run]
    print(json.dumps(rows, indent=2))
    out = Path(a.run[0]) / "evaluation.json"
    out.write_text(json.dumps({"gold_promos": len(gold), "iou_threshold": a.iou, "results": rows}, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
