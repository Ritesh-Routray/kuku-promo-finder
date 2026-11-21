"""Stage: score, flag for review, and rank with variety (MMR)."""
from __future__ import annotations

import numpy as np

from .heartbeat import window_intensity
from .signals import embed
from .snap import tiou

RISK = {"low": 0.0, "medium": 0.5, "high": 1.0}


def score_promo(p: dict, judge: dict, heartbeats: dict, n_eps: int, weights: dict) -> dict:
    s0 = p["segments"][0]
    parts = {
        "hook": judge["three_sec"]["score"] / 10,
        "cliffhanger": judge["cliffhanger"]["score"] / 10 * (1.0 if judge["cliffhanger"]["unresolved"] else 0.6),
        "suspense": judge.get("suspense", 0.5),
        "standalone": judge["cold_viewer"]["clarity"] / 10 * (1.0 if judge["cold_viewer"]["understood"] else 0.5),
        "heartbeat": window_intensity(heartbeats[s0["ep"]]["curve"], s0["start"], s0["start"] + 3),
        "early_episode": 1 - (p["ep"] - 1) / max(n_eps - 1, 1),
        "ad_risk": RISK.get(judge["ad_risk"]["level"], 0.0),
    }
    total = sum(weights.get(k, 0) * v for k, v in parts.items())
    max_total = sum(w for w in weights.values() if w > 0)
    return {"score": round(100 * total / max_total, 1), "parts": {k: round(v, 3) for k, v in parts.items()}}


def review_reasons(p: dict, judge: dict) -> list[str]:
    r = []
    parts = p["scores"]["parts"]
    if not judge["cold_viewer"]["understood"]:
        r.append("a new viewer may not follow it")
    if parts["heartbeat"] > 0.7 and parts["hook"] < 0.5:
        r.append("heartbeat says intense but 3-second judge disagrees")
    if parts["heartbeat"] < 0.3 and parts["hook"] > 0.7:
        r.append("3-second judge likes it but script intensity is low (check the visual)")
    if judge["ad_risk"]["level"] != "low":
        r.append(f"ad-policy risk {judge['ad_risk']['level']}: {judge['ad_risk']['reason']}")
    if not judge["cliffhanger"]["unresolved"]:
        r.append("ending may resolve the question")
    r += [f for f in p.get("flags", []) if "not found" in f or "extended" in f or "same line" in f]
    return r


def mmr_rank(promos: list[dict], embed_model: str, lam: float, top_n: int) -> list[dict]:
    if not promos:
        return []
    texts = [f"{p['archetype']}. {p['hook_line']} {p['cliffhanger_line']} {p['open_question']}" for p in promos]
    v = embed(texts, embed_model)
    sim_text = v @ v.T
    rel = np.array([p["scores"]["score"] / 100 for p in promos])
    chosen: list[int] = []
    rest = list(range(len(promos)))
    while rest and len(chosen) < top_n:
        def mmr(i):
            if not chosen:
                return rel[i]
            div = max(max(tiou(promos[i], promos[j]), float(sim_text[i, j]) ** 2) for j in chosen)
            return lam * rel[i] - (1 - lam) * div
        best = max(rest, key=mmr)
        chosen.append(best)
        rest.remove(best)
    ranked = [promos[i] for i in chosen]
    for r, p in enumerate(ranked, 1):
        p["rank"] = r
    return ranked
