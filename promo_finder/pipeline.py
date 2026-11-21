"""Orchestrates every stage and writes a run folder."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .candidates import heuristic_candidates, llm_candidates
from .config import load_config
from .export import write_outputs
from .heartbeat import build_heartbeats
from .judges import heuristic_judge, llm_judge
from .llm import LLM, LLMError
from .memory import StoryMemory
from .parse import parse_folder
from .rank import mmr_rank, review_reasons, score_promo
from .signals import emotion_scores
from .snap import Snapper, tiou

Progress = Callable[[str, float, str], None]


def _noop(stage: str, pct: float, msg: str) -> None:
    print(f"[{stage:<10}] {pct:5.1f}%  {msg}", flush=True)


def run(input_dir: str | Path, out_dir: str | Path, cfg: dict | None = None, show: str | None = None,
        api_keys: dict | None = None, progress: Progress = _noop, episodes_limit: int | None = None) -> dict:
    t0 = time.time()
    cfg = cfg or load_config()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    show = show or Path(input_dir).name.split("-scripts")[0]
    errors: list[str] = []

    progress("parse", 2, "Reading screenplays")
    episodes = parse_folder(input_dir)
    if episodes_limit:
        episodes = episodes[:episodes_limit]
    if not episodes:
        raise ValueError("No screenplay .txt files with timestamped lines found.")
    by_ep = {e.ep: e for e in episodes}
    progress("parse", 5, f"{len(episodes)} episodes, {sum(len(e.lines) for e in episodes)} lines")

    progress("signals", 8, "Scoring emotion on every line (local model)")
    emo = emotion_scores(episodes, cfg["local_models"]["emotion"], cfg["cache_dir"])
    hb = build_heartbeats(episodes, emo, cfg["heartbeat"]["peaks_per_episode"], cfg["heartbeat"]["min_peak_gap_sec"])
    progress("heartbeat", 15, "Drama heartbeat built")

    progress("memory", 17, "Indexing scenes for story memory")
    memory = StoryMemory(episodes, cfg["local_models"]["embeddings"])

    llm = LLM(cfg, api_keys)
    raw_cands: list[dict] = []
    contexts: dict[int, dict] = {}
    k = cfg["promo"]["candidates_per_episode"]
    for i, ep in enumerate(episodes):
        progress("candidates", 20 + 40 * i / len(episodes), f"Episode {ep.ep}: finding promo moments")
        try:
            if llm.is_heuristic("generator"):
                cands = heuristic_candidates(ep, hb[ep.ep], cfg)
            else:
                cands, contexts[ep.ep] = llm_candidates(llm, ep, len(episodes), show, hb[ep.ep], memory, k)
        except LLMError as e:
            errors.append(f"ep {ep.ep} candidates: {e}")
            progress("candidates", 20 + 40 * i / len(episodes), f"Episode {ep.ep}: LLM failed, using heuristic")
            cands = heuristic_candidates(ep, hb[ep.ep], cfg)
        for c in cands:
            raw_cands.append({**c, "ep": ep.ep})

    progress("rules", 61, "Snapping cuts and checking rules")
    passed, rejected = [], []
    for c in raw_cands:
        clip, reason = Snapper(by_ep[c["ep"]], cfg).build(c)
        if clip is None:
            rejected.append({"ep": c["ep"], "title": c.get("title", ""), "reason": reason, "segments": c["segments"]})
            continue
        if any(q["ep"] == clip["ep"] and tiou(q, clip) > 0.8 for q in passed):
            rejected.append({"ep": c["ep"], "title": c.get("title", ""), "reason": "duplicate of another candidate",
                             "segments": c["segments"]})
            continue
        clip["id"] = f"e{clip['ep']:03d}_{len([q for q in passed if q['ep'] == clip['ep']]) + 1}"
        passed.append(clip)

    progress("judges", 65, f"Judging {len(passed)} clips as a cold viewer")
    items = [(p["id"], by_ep[p["ep"]], p) for p in passed]
    judged: dict[str, dict] = {}
    if llm.is_heuristic("judge"):
        judged = heuristic_judge(items, hb)
    else:
        # Batches never mix episodes, so changing one episode's clips only re-judges that episode (cache).
        bs = cfg["judge"]["batch_size"]
        batches: list[list] = []
        for it in items:
            if batches and len(batches[-1]) < bs and batches[-1][0][2]["ep"] == it[2]["ep"]:
                batches[-1].append(it)
            else:
                batches.append([it])
        done = 0
        for b in batches:
            progress("judges", 65 + 25 * done / max(len(items), 1),
                     f"Judging episode {b[0][2]['ep']} ({done + 1}-{done + len(b)} of {len(items)})")
            try:
                judged.update(llm_judge(llm, b, cfg))
            except LLMError as e:
                errors.append(f"judge ep {b[0][2]['ep']}: {str(e)[:300]}")
            done += len(b)
        missing = [it for it in items if it[0] not in judged]
        if missing:
            judged.update(heuristic_judge(missing, hb))
            for m in missing:
                judged[m[0]]["fallback"] = True

    progress("rank", 92, "Scoring and ranking")
    for p in passed:
        p["judge"] = judged[p["id"]]
        p["scores"] = score_promo(p, p["judge"], hb, len(episodes), cfg["rank"]["weights"])
        p["review_reasons"] = review_reasons(p, p["judge"])
    ranked = mmr_rank(sorted(passed, key=lambda p: -p["scores"]["score"]), cfg["local_models"]["embeddings"],
                      cfg["rank"]["mmr_lambda"], cfg["rank"]["top_n"])

    progress("export", 96, "Writing outputs")
    meta = {"show": show, "episodes": len(episodes), "candidates": len(raw_cands),
            "models": {r: cfg["models"][r] for r in ("generator", "judge")}}
    write_outputs(out, ranked, passed, rejected, meta)
    (out / "episodes.json").write_text(json.dumps([e.to_dict() for e in episodes], ensure_ascii=False), encoding="utf-8")
    (out / "heartbeats.json").write_text(json.dumps({str(k): {"curve": v["curve"], "peaks": v["peaks"]}
                                                     for k, v in hb.items()}), encoding="utf-8")
    (out / "contexts.json").write_text(json.dumps({str(k): v for k, v in contexts.items()}, ensure_ascii=False, default=str), encoding="utf-8")
    log = {**meta, "started": datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
           "seconds": round(time.time() - t0, 1), "passed_rules": len(passed), "rejected": len(rejected),
           "ranked": len(ranked), "llm": llm.summary(), "errors": errors,
           "config": {k: cfg[k] for k in ("models", "promo", "heartbeat", "rank")}}
    (out / "run_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    progress("done", 100, f"{len(ranked)} promos ranked in {log['seconds']}s")
    return log
