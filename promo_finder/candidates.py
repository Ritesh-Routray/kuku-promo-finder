"""Stage: propose promo candidates per episode (LLM with retrieved context, or an offline heuristic)."""
from __future__ import annotations

from .llm import LLM, prompt
from .memory import StoryMemory
from .parse import Episode, fmt_time, render_lines
from .schemas import CandidatesOut


def llm_candidates(llm: LLM, ep: Episode, total: int, show: str, hb: dict, memory: StoryMemory,
                   k: int) -> tuple[list[dict], dict]:
    peaks = hb["peaks"]
    peak_text = " ".join(l.text for l in ep.lines if l.kind != "camera"
                         and any(abs(l.start - p) <= 4 for p in peaks))
    related = memory.related(ep.ep, f"{ep.logline} {peak_text}"[:1500], k=3)
    user = prompt("candidates", show=show, ep=ep.ep, total=total, duration=fmt_time(ep.duration),
                  previously=memory.previously(ep.ep), related=memory.format_related(related),
                  peaks=", ".join(fmt_time(p) for p in peaks) or "(none)",
                  script=render_lines(ep.lines, with_camera=True), k=k)
    out = llm.json("generator", prompt("candidates_system"), user, schema=CandidatesOut, tag=f"candidates_ep{ep.ep}")
    context = {"previously": memory.previously(ep.ep), "related": related, "peaks": peaks}
    return out["promos"], context


def heuristic_candidates(ep: Episode, hb: dict, cfg: dict) -> list[dict]:
    """Offline stand-in: hook = strongest line near each heartbeat peak; end = strongest line 25-50s later."""
    scores = hb["lines"]
    lines = [l for l in ep.lines if l.kind in ("dialogue", "action", "sfx")]
    out = []
    for p in hb["peaks"]:
        near = [l for l in lines if abs(l.start - p) <= 4]
        if not near:
            continue
        hook = max(near, key=lambda l: scores[l.idx]["score"])
        lo, hi = hook.start + cfg["promo"]["min_sec"] + 3, hook.start + cfg["promo"]["max_sec"] - 8
        tail = [l for l in lines if lo <= l.end <= hi]
        if not tail:
            tail = [l for l in lines if l.end > hook.start + 10] or [lines[-1]]
        cliff = max(tail, key=lambda l: scores[l.idx]["score"] + (0.5 if "?" in l.text else 0))
        out.append({"title": f"Ep {ep.ep} peak {fmt_time(p)}",
                    "segments": [{"start": hook.start, "end": cliff.end}],
                    "hook_line": hook.text, "cliffhanger_line": cliff.text,
                    "open_question": "", "archetype": "other",
                    "why": "Heuristic: highest-intensity line near a heartbeat peak."})
    return out
