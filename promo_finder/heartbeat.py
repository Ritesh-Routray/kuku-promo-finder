"""Drama heartbeat: a per-second intensity curve for each episode, from cheap signals.

Signals per line: emotion model arousal, the script's own emotion tags, dramatic event words,
punctuation, short punchy lines, sound-FX stings, and how fast the camera is cutting.
"""
from __future__ import annotations

import re

import numpy as np

from .parse import Episode, Line

EVENT_WORDS = {
    # physical / violent
    "slap": 3, "slaps": 3, "slapped": 3, "strike": 2, "strikes": 2, "punch": 3, "shove": 2, "shoves": 2,
    "grab": 1.5, "grabs": 1.5, "throws": 1.5, "hurls": 2, "collapses": 2.5, "faints": 2.5, "blood": 2.5,
    "bleeding": 2.5, "knife": 2.5, "dagger": 2.5, "sword": 2, "gun": 2.5, "pistol": 2.5, "poison": 3,
    "kneel": 2, "kneels": 2, "chokes": 2.5, "shatters": 2, "smashes": 2, "tears": 1, "rips": 1.5,
    "kicks": 2, "drags": 1.5, "fire": 1.5, "dead": 2.5, "die": 2, "dies": 2.5, "kill": 3, "murder": 3,
    # reveal / relationship
    "duke": 2, "secret": 2, "reveal": 2, "reveals": 2, "truth": 1.5, "pregnant": 3, "divorce": 2.5,
    "betray": 2.5, "betrayed": 2.5, "liar": 2, "married": 1.5, "marry": 1.5, "wedding": 1, "heir": 1.5,
    "kiss": 2, "kisses": 2, "disowned": 2.5, "banished": 2, "arrest": 2, "arrested": 2, "guilty": 2,
    "scandal": 2, "ruined": 2, "beggar": 1.5, "cripple": 2, "crippled": 2, "illegitimate": 2.5,
    "gasps": 1.5, "screams": 2, "shouts": 1, "sobs": 1, "frozen": 1, "stunned": 1.5, "shocked": 1.5,
}
HOT_TAGS = {
    "furious", "screaming", "venomous", "enraged", "shocked", "horrified", "desperate", "sobbing",
    "menacing", "threatening", "taunting", "mocking", "spiteful", "scornful", "cold", "icy", "commanding",
    "unyielding", "fierce", "panicked", "terrified", "heartbroken", "seething", "outraged", "defiant",
    "hysterical", "shouting", "vicious", "cruel", "smug", "scheming", "stunned", "trembling", "breathless",
}
SFX_WORDS = {"sting": 2, "cliffhanger": 3, "swell": 1.5, "swells": 1.5, "slam": 2, "crack": 2, "thud": 1.5,
             "gasp": 1.5, "boom": 2, "shatter": 2, "crash": 2, "drone": 1, "ominous": 1.5, "heartbeat": 1.5,
             "silence": 1, "whoosh": 1, "impact": 2}
AROUSAL = {"anger": 1.0, "fear": 0.9, "surprise": 0.8, "disgust": 0.8, "sadness": 0.5, "joy": 0.2, "neutral": 0.0}

WORD_RE = re.compile(r"[a-z']+")


def line_score(line: Line, emo: dict | None) -> tuple[float, dict]:
    words = WORD_RE.findall(line.text.lower())
    parts = {"event": 0.0, "tag": 0.0, "emotion": 0.0, "punct": 0.0, "punch": 0.0, "sfx": 0.0}
    parts["event"] = min(sum(EVENT_WORDS.get(w, 0) for w in words), 6) / 2
    if line.kind == "dialogue":
        tags = {t.lower() for tag in line.tags for t in re.findall(r"[a-z]+", tag.lower())}
        parts["tag"] = min(len(tags & HOT_TAGS), 2) * 0.8
        if emo:
            parts["emotion"] = sum(AROUSAL.get(k, 0) * v for k, v in emo.items()) * 2
        parts["punct"] = min(line.text.count("!"), 2) * 0.5 + (0.3 if "?" in line.text else 0)
        if 0 < len(words) <= 6:
            parts["punch"] = 0.5
    elif line.kind == "sfx":
        parts["sfx"] = min(sum(SFX_WORDS.get(w, 0) for w in words), 4) / 1.5
    elif line.kind == "camera":
        if any(w in words for w in ("close", "extreme", "insert", "snap", "whip", "crash")):
            parts["punch"] = 0.3
    return sum(parts.values()), parts


def episode_curve(ep: Episode, emotions: dict) -> dict:
    """Per-second curve (0-1), per-line scores, and the cut-density signal."""
    n = int(np.ceil(ep.duration)) + 1
    curve = np.zeros(n)
    line_scores = {}
    for l in ep.lines:
        s, parts = line_score(l, emotions.get((ep.ep, l.idx)))
        line_scores[l.idx] = {"score": round(s, 3), "parts": {k: round(v, 3) for k, v in parts.items() if v}}
        a, b = int(l.start), min(int(np.ceil(l.end)) + 1, n)
        if b <= a:
            b = min(a + 1, n)
        curve[a:b] = np.maximum(curve[a:b], s)
    # cut density: camera shots starting within each 4s window
    cuts = np.zeros(n)
    for l in ep.lines:
        if l.kind == "camera":
            cuts[min(int(l.start), n - 1)] += 1
    cut_density = np.convolve(cuts, np.ones(4), mode="same")
    curve = curve + 0.25 * cut_density
    # smooth with a small gaussian
    k = np.exp(-0.5 * (np.arange(-3, 4) / 1.5) ** 2)
    curve = np.convolve(curve, k / k.sum(), mode="same")
    if curve.max() > 0:
        curve = curve / curve.max()
    return {"curve": curve, "lines": line_scores}


def find_peaks(curve: np.ndarray, k: int, min_gap: int) -> list[int]:
    order = np.argsort(-curve)
    peaks: list[int] = []
    for t in order:
        if curve[t] <= 0:
            break
        if all(abs(int(t) - p) >= min_gap for p in peaks):
            peaks.append(int(t))
        if len(peaks) >= k:
            break
    return sorted(peaks)


def build_heartbeats(episodes: list[Episode], emotions: dict, k: int, min_gap: int) -> dict[int, dict]:
    out = {}
    for ep in episodes:
        c = episode_curve(ep, emotions)
        out[ep.ep] = {
            "curve": [round(float(x), 3) for x in c["curve"]],
            "peaks": find_peaks(c["curve"], k, min_gap),
            "lines": c["lines"],
        }
    return out


def window_intensity(curve: list[float], start: float, end: float) -> float:
    a, b = int(start), max(int(np.ceil(end)), int(start) + 1)
    seg = curve[a:b]
    return float(max(seg)) if seg else 0.0
