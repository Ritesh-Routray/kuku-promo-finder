"""Stage: judge each clip as a stranger would (cold viewer, 3-second test, cliffhanger, suspense, ad risk)."""
from __future__ import annotations

import math
import re

import numpy as np

from .heartbeat import EVENT_WORDS, window_intensity
from .llm import LLM, prompt
from .parse import Episode, fmt_time
from .schemas import JudgeOut
from .signals import embed
from .snap import clip_lines

VIOLENT = {"slap", "slaps", "slapped", "punch", "blood", "bleeding", "knife", "dagger", "gun", "pistol",
           "kill", "murder", "chokes", "kicks", "strikes", "poison", "dead", "sword"}


def clip_text(ep: Episode, clip: dict, first_sec: float | None = None, with_camera: bool = True) -> str:
    rows = []
    for off, l in clip_lines(ep, clip["segments"]):
        if first_sec is not None and off > first_sec:
            break
        if l.kind == "camera" and not with_camera:
            continue
        who = {"dialogue": l.speaker + (f" ({', '.join(l.tags)})" if l.tags else ""),
               "action": "ACTION", "sfx": "SFX", "camera": "CAMERA"}.get(l.kind, l.kind.upper())
        rows.append(f"[{fmt_time(off)}] {who}: {l.text}")
    return "\n".join(rows)


def next_text(ep: Episode, clip: dict, seconds: float = 20) -> str:
    end = clip["segments"][-1]["end"]
    return " ".join(l.text for l in ep.lines if l.kind in ("dialogue", "action")
                    and end <= l.start < end + seconds)[:600]


def suspense_from_outcomes(outcomes: list[dict]) -> float:
    """Normalised entropy of the 'what happens next' distribution: 1 = wide open, 0 = obvious."""
    ps = np.array([max(o["p"], 1e-6) for o in outcomes], dtype=float)
    ps = ps / ps.sum()
    if len(ps) < 2:
        return 0.0
    return float(-(ps * np.log(ps)).sum() / math.log(len(ps)))


def suspense_score(outcomes: list[dict], embed_model: str) -> tuple[float, dict]:
    """LLM probabilities come back near-templated (0.4/0.25/0.2/0.15), so entropy alone saturates.
    Blend: how unsure the top guess is + how semantically different the guesses are."""
    if len(outcomes) < 2:
        return 0.0, {}
    ps = np.array([max(o["p"], 1e-6) for o in outcomes], dtype=float)
    ps = ps / ps.sum()
    n = len(ps)
    open_top = float((1 - ps.max()) / (1 - 1 / n))
    v = embed([o["outcome"] for o in outcomes], embed_model)
    sims = v @ v.T
    spread = float(1 - sims[np.triu_indices(n, 1)].mean())       # ~0.15 (same idea) .. ~0.5 (very different)
    spread_n = float(np.clip((spread - 0.15) / 0.35, 0, 1))
    return round(0.4 * open_top + 0.6 * spread_n, 3), {"entropy": round(suspense_from_outcomes(outcomes), 3),
                                                       "top_open": round(open_top, 3), "spread": round(spread, 3)}


def surprise(outcomes: list[dict], actual: str, embed_model: str) -> float:
    """How far what really happens next is from the guesses (1 = nobody saw it coming)."""
    if not actual or not outcomes:
        return 0.0
    v = embed([actual] + [o["outcome"] for o in outcomes], embed_model)
    sims = v[1:] @ v[0]
    ps = np.array([o["p"] for o in outcomes], dtype=float)
    ps = ps / ps.sum() if ps.sum() > 0 else np.ones_like(ps) / len(ps)
    return float(np.clip(1 - float((ps * sims).sum()), 0, 1))


def llm_judge(llm: LLM, items: list[tuple[str, Episode, dict]], cfg: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    bs = cfg["judge"]["batch_size"]
    emb = cfg["local_models"]["embeddings"]
    for i in range(0, len(items), bs):
        batch = items[i:i + bs]
        blocks = []
        for cid, ep, clip in batch:
            blocks.append(f"=== CLIP id={cid} ({clip['duration']:.0f}s) ===\nFIRST 3 SECONDS:\n"
                          f"{clip_text(ep, clip, first_sec=3.0) or '(nothing)'}\nFULL CLIP:\n{clip_text(ep, clip)}")
        res = llm.json("judge", prompt("judge_system"), prompt("judge", n=len(batch), clips="\n\n".join(blocks)),
                       schema=JudgeOut, tag=f"judge_batch{i // bs}")
        got = {c["id"]: c for c in res["clips"]}
        for cid, ep, clip in batch:
            j = got.get(cid)
            if j is None:
                continue
            j["suspense"], j["suspense_parts"] = suspense_score(j["outcomes"], emb)
            actual = next_text(ep, clip)
            j["what_really_happens"] = actual
            j["surprise"] = round(surprise(j["outcomes"], actual, emb), 3)
            out[cid] = j
    return out


def heuristic_judge(items: list[tuple[str, Episode, dict]], heartbeats: dict) -> dict[str, dict]:
    out = {}
    for cid, ep, clip in items:
        curve = heartbeats[ep.ep]["curve"]
        s0 = clip["segments"][0]["start"]
        e1 = clip["segments"][-1]["end"]
        hook = window_intensity(curve, s0, s0 + 3)
        cliff = window_intensity(curve, e1 - 5, e1)
        text = clip_text(ep, clip).lower()
        words = set(re.findall(r"[a-z]+", text))
        risk = "high" if len(words & VIOLENT) >= 2 else "medium" if words & VIOLENT else "low"
        n_lines = text.count("\n") + 1
        out[cid] = {
            "cold_viewer": {"who": "", "what": "", "want_next": "", "understood": n_lines >= 6,
                            "clarity": int(np.clip(3 + n_lines // 3, 1, 8))},
            "three_sec": {"stop": hook > 0.6, "score": int(np.clip(round(hook * 10), 1, 10)), "why": "heartbeat"},
            "cliffhanger": {"unresolved": cliff > 0.5 or "?" in text[-200:],
                            "score": int(np.clip(round(cliff * 10), 1, 10))},
            "outcomes": [], "ad_risk": {"level": risk, "reason": "violence keywords" if risk != "low" else ""},
            "suspense": 0.5, "surprise": 0.0, "what_really_happens": next_text(ep, clip),
        }
    return out
