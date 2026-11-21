"""Turn rough LLM timestamps into clean, rule-checked clips. Pure code."""
from __future__ import annotations

import difflib
import re

from .parse import Episode, Line, to_seconds


def _sec(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().strip("()[]")
    try:
        return to_seconds(s)
    except ValueError:
        m = re.findall(r"[\d.]+", s)
        return float(m[0]) if m else 0.0


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower())


def find_line(lines: list[Line], text: str, lo: float, hi: float, allow_camera: bool = False) -> Line | None:
    """Best fuzzy match for `text` among dialogue/action/sfx lines inside [lo, hi]."""
    # The LLM sometimes quotes a CAMERA line as the hook ("CAMERA: Close-up of ..."); allow those only then.
    camera_ok = allow_camera or text.strip().upper().startswith("CAMERA")
    target = _norm(re.sub(r"^\s*(CAMERA|ACTION|SFX|SOUND FX)\s*:\s*", "", text, flags=re.I))
    if not target:
        return None
    best, best_r = None, 0.0
    for l in lines:
        if (l.kind == "camera" and not camera_ok) or l.end < lo - 0.5 or l.start > hi + 0.5:
            continue
        cand = _norm(l.text)
        if not cand:
            continue
        r = 1.0 if (target in cand or cand in target) and len(cand) > 3 else \
            difflib.SequenceMatcher(None, target, cand).ratio()
        if r > best_r:
            best, best_r = l, r
    return best if best_r >= 0.55 else None


class Snapper:
    def __init__(self, ep: Episode, cfg: dict):
        self.ep = ep
        self.cfg = cfg["promo"]
        self.starts = sorted({l.start for l in ep.lines})
        self.ends = sorted({l.end for l in ep.lines})

    def snap_start(self, t: float) -> float:
        c = [s for s in self.starts if s <= t + 0.3]
        return c[-1] if c else self.starts[0]

    def snap_end(self, t: float) -> float:
        c = [e for e in self.ends if e >= t - 0.3]
        return c[0] if c else self.ends[-1]

    def build(self, cand: dict) -> tuple[dict | None, str]:
        """Return (clip, '') or (None, rejection_reason)."""
        segs = []
        for s in cand["segments"][: self.cfg["max_segments"] + 1]:
            a, b = _sec(s["start"]), _sec(s["end"])
            if b <= a:
                continue
            a, b = max(0.0, a), min(b, self.ep.duration)
            segs.append([self.snap_start(a), self.snap_end(b)])
        if not segs:
            return None, "no valid segments"
        segs.sort()
        merged = [segs[0]]
        for a, b in segs[1:]:
            if a <= merged[-1][1] + 1.0:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        if len(merged) > self.cfg["max_segments"]:
            return None, f"too many segments ({len(merged)})"
        flags = []

        # Hook: must begin within hook_within_sec of the clip start.
        hook = find_line(self.ep.lines, cand.get("hook_line", ""), merged[0][0], merged[0][1])
        if hook is None:
            hook = find_line(self.ep.lines, cand.get("hook_line", ""), merged[0][0] - 10, merged[-1][1])
        if hook is not None:
            if hook.start - merged[0][0] > self.cfg["hook_within_sec"] or hook.start < merged[0][0]:
                new_start = hook.start  # a line start is already a clean cut; snapping could land just after it
                if new_start < merged[0][1]:
                    merged[0][0] = new_start
                    flags.append("start moved to hook")
        else:
            flags.append("hook line not found in script")

        # Cliffhanger: cut right after it.
        cliff = find_line(self.ep.lines, cand.get("cliffhanger_line", ""), merged[-1][0], merged[-1][1] + 8)
        if cliff is not None:
            # end on the first boundary at/after the cliffhanger line (a shot may run slightly past it)
            later = [e for e in self.ends if cliff.end <= e <= cliff.end + 1.5]
            target_end = later[-1] if later else cliff.end
            if abs(target_end - merged[-1][1]) > 0.5 and target_end > merged[-1][0]:
                merged[-1][1] = target_end
                flags.append("end moved to cliffhanger")
        else:
            flags.append("cliffhanger line not found in script")

        dur = sum(b - a for a, b in merged)
        if dur < self.cfg["min_sec"]:
            # Too short. Never stretch past the cliffhanger: the ending is the point of the promo.
            # 1) Pull the start earlier into the setup, but only as far as keeps the hook within the first 3 s.
            need = self.cfg["min_sec"] - dur
            cur = merged[0][0]
            earliest = (hook.start - self.cfg["hook_within_sec"]) if hook is not None else cur - need - 1.0
            options = [s for s in self.starts if earliest - 1e-6 <= s < cur]
            enough = [s for s in options if cur - s >= need]
            if options:
                merged[0][0] = max(enough) if enough else min(options)
                flags.append("start moved earlier into the setup")
            dur = sum(b - a for a, b in merged)
            # 2) Only when there is no cliffhanger line to protect may the end move later.
            if dur < self.cfg["min_sec"] and cliff is None:
                need = self.cfg["min_sec"] - dur
                # +0.35 so the snap tolerance (0.3s) can't land just under the minimum
                merged[-1][1] = self.snap_end(min(merged[-1][1] + need + 0.35, self.ep.duration))
                dur = sum(b - a for a, b in merged)
                flags.append("end extended to reach minimum length")
            if dur < self.cfg["min_sec"]:
                return None, f"too short ({dur:.1f}s) without cutting past the cliffhanger"
        if dur > self.cfg["max_sec"]:
            return None, f"too long ({dur:.1f}s)"

        if hook is not None and cliff is not None and hook.idx == cliff.idx:
            flags.append("hook and cliffhanger are the same line")
        hook_at = (hook.start - merged[0][0]) if hook is not None else None
        if hook_at is not None and hook_at > self.cfg["hook_within_sec"]:
            return None, f"hook starts too late ({hook_at:.1f}s)"

        return {
            "ep": self.ep.ep,
            "segments": [{"ep": self.ep.ep, "start": round(a, 2), "end": round(b, 2)} for a, b in merged],
            "duration": round(dur, 2),
            "hook_line": hook.text if hook else cand.get("hook_line", ""),
            "hook_speaker": hook.speaker if hook else "",
            "hook_at": round(hook_at, 2) if hook_at is not None else None,
            "cliffhanger_line": cliff.text if cliff else cand.get("cliffhanger_line", ""),
            "title": cand.get("title", ""),
            "open_question": cand.get("open_question", ""),
            "archetype": cand.get("archetype", "other"),
            "why": cand.get("why", ""),
            "flags": flags,
        }, ""


def clip_lines(ep: Episode, segments: list[dict]) -> list[tuple[float, Line]]:
    """Lines inside the clip with their offset on the promo's own timeline."""
    out, offset = [], 0.0
    for s in segments:
        for l in ep.lines:
            if l.start >= s["start"] - 0.05 and l.start < s["end"]:
                out.append((offset + l.start - s["start"], l))
        offset += s["end"] - s["start"]
    return out


def tiou(a: dict, b: dict) -> float:
    """Temporal IoU between two promos (sum over overlapping segments of the same episode)."""
    inter = 0.0
    for x in a["segments"]:
        for y in b["segments"]:
            if x["ep"] == y["ep"]:
                inter += max(0.0, min(x["end"], y["end"]) - max(x["start"], y["start"]))
    la = sum(s["end"] - s["start"] for s in a["segments"])
    lb = sum(s["end"] - s["start"] for s in b["segments"])
    union = la + lb - inter
    return inter / union if union > 0 else 0.0
