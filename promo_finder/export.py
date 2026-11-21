"""Stage: write raw outputs (CSV, JSON, Markdown report, EDL timelines)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .parse import fmt_time

FPS = 30


def _tc(sec: float) -> str:
    f = int(round(sec * FPS))
    h, rem = divmod(f, 3600 * FPS)
    m, rem = divmod(rem, 60 * FPS)
    s, fr = divmod(rem, FPS)
    return f"{h:02d}:{m:02d}:{s:02d}:{fr:02d}"


def seg_str(p: dict) -> str:
    return "; ".join(f"EP{s['ep']:03d} {fmt_time(s['start'])}-{fmt_time(s['end'])}" for s in p["segments"])


def write_edl(p: dict, path: Path) -> None:
    rows = [f"TITLE: PROMO {p['rank']:02d} {p['title'][:40].upper()}", "FCM: NON-DROP FRAME", ""]
    rec = 0.0
    for i, s in enumerate(p["segments"], 1):
        dur = s["end"] - s["start"]
        rows.append(f"{i:03d}  EP{s['ep']:03d}    V     C        {_tc(s['start'])} {_tc(s['end'])} {_tc(rec)} {_tc(rec + dur)}")
        rows.append(f"* FROM CLIP NAME: EPISODE {s['ep']}")
        rec += dur
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_outputs(out: Path, ranked: list[dict], all_promos: list[dict], rejected: list[dict], meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "edl").mkdir(exist_ok=True)
    (out / "promos_ranked.json").write_text(json.dumps(ranked, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "candidates_all.json").write_text(json.dumps(all_promos, indent=2, ensure_ascii=False), encoding="utf-8")

    cols = ["rank", "id", "title", "segments", "duration_sec", "hook_line", "hook_at_sec", "cliffhanger_line",
            "open_question", "why", "archetype", "score", "hook", "cliffhanger", "suspense", "standalone",
            "heartbeat", "ad_risk", "needs_review", "review_reasons"]
    with open(out / "promos_ranked.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in ranked:
            pt = p["scores"]["parts"]
            w.writerow([p["rank"], p["id"], p["title"], seg_str(p), p["duration"], p["hook_line"], p["hook_at"],
                        p["cliffhanger_line"], p["open_question"], p["why"], p["archetype"], p["scores"]["score"],
                        pt["hook"], pt["cliffhanger"], pt["suspense"], pt["standalone"], pt["heartbeat"],
                        p["judge"]["ad_risk"]["level"], bool(p["review_reasons"]), " | ".join(p["review_reasons"])])

    with open(out / "rejected.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ep", "title", "reason", "segments_proposed"])
        for r in rejected:
            w.writerow([r["ep"], r.get("title", ""), r["reason"], json.dumps(r.get("segments", []))])

    for p in ranked:
        write_edl(p, out / "edl" / f"promo_{p['rank']:02d}.edl")

    md = [f"# Promo report: {meta['show']}", "",
          f"Episodes: {meta['episodes']} | Candidates: {meta['candidates']} | Passed rules: {len(all_promos)} | "
          f"Rejected: {len(rejected)} | Ranked: {len(ranked)}",
          f"Models: generator `{meta['models']['generator']}`, judge `{meta['models']['judge']}`", ""]
    for p in ranked:
        j = p["judge"]
        md += [f"## {p['rank']}. {p['title']}  (score {p['scores']['score']})",
               f"- **Segments:** {seg_str(p)} ({p['duration']:.0f}s)",
               f"- **Hook** (at {p['hook_at']}s): {p['hook_line']}",
               f"- **Cliffhanger:** {p['cliffhanger_line']}",
               f"- **Open question:** {p['open_question']}",
               f"- **Why it works:** {p['why']}",
               f"- **3-second test:** {j['three_sec']['score']}/10, {j['three_sec']['why']}",
               f"- **Cold viewer:** understood={j['cold_viewer']['understood']}, clarity {j['cold_viewer']['clarity']}/10. "
               f"{j['cold_viewer']['what']}",
               f"- **Suspense:** {j.get('suspense', 0):.2f}  |  **Surprise vs real next scene:** {j.get('surprise', 0):.2f}",
               f"- **Ad risk:** {j['ad_risk']['level']} {j['ad_risk']['reason']}"]
        if p["review_reasons"]:
            md.append(f"- **Needs review:** {'; '.join(p['review_reasons'])}")
        md.append("")
    (out / "promos_report.md").write_text("\n".join(md), encoding="utf-8")
