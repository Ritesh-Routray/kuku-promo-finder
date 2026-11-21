"""Parse Kuku screenplay .txt files into timestamped rows. Pure code, no AI."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

BLOCK_RE = re.compile(r"^\*\*(?P<head>.+?):?\*\*:?\s*$")
TIME_RE = re.compile(r"Start:\s*\(?(?P<s>[\d:.]+)\)?\s*\|\s*End:\s*\(?(?P<e>[\d:.]+)\)?")
SCENE_RE = re.compile(r"^SCENE\s+(\d+)", re.I)
NON_DIALOGUE = {"CAMERA", "ACTION", "SOUND FX", "SFX", "SOUND", "MUSIC", "TEXT", "SUPER", "TITLE"}
SPEAKER_PREFIXES = ("LADY ", "LORD ", "SIR ", "THE ", "DUKE ", "DUCHESS ")


def to_seconds(t: str) -> float:
    parts = [float(p) for p in t.strip().split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return round(sec, 2)


def fmt_time(sec: float) -> str:
    m, s = divmod(max(sec, 0.0), 60)
    return f"{int(m):02d}:{s:05.2f}"


@dataclass
class Line:
    ep: int
    idx: int
    scene: int
    heading: str
    kind: str            # camera | action | sfx | dialogue | other
    speaker: str         # canonical speaker for dialogue, else ""
    raw_speaker: str
    tags: list[str]
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Episode:
    ep: int
    file: str
    logline: str
    continuity: str
    duration: float
    lines: list[Line] = field(default_factory=list)

    def to_dict(self, with_lines: bool = True) -> dict:
        d = {k: getattr(self, k) for k in ("ep", "file", "logline", "continuity", "duration")}
        if with_lines:
            d["lines"] = [l.to_dict() for l in self.lines]
        return d


def canonical_speaker(name: str, aliases: dict[str, str] | None = None) -> str:
    n = re.sub(r"\s+", " ", name.upper()).strip()
    if aliases and n in aliases:
        return aliases[n]
    for p in SPEAKER_PREFIXES:
        rest = n[len(p):]
        # "LADY ELEANOR" -> "ELEANOR", but keep descriptions like "LADY IN GOLD GOWN"
        if n.startswith(p) and rest and (p == "THE " or " " not in rest):
            n = rest
            break
    if aliases and n in aliases:
        return aliases[n]
    return n


def _split_head(head: str) -> tuple[str, list[str]]:
    tags = []
    for grp in re.findall(r"\(([^)]*)\)", head):
        tags += [t.strip() for t in grp.split(",") if t.strip()]
    name = re.sub(r"\([^)]*\)", "", head).strip().rstrip(":").strip()
    return name, tags


def _kind(name: str) -> str:
    u = name.upper()
    if u == "CAMERA":
        return "camera"
    if u == "ACTION":
        return "action"
    if u in ("SOUND FX", "SFX", "SOUND", "MUSIC"):
        return "sfx"
    if u in NON_DIALOGUE:
        return "other"
    return "dialogue"


def parse_episode(path: str | Path, aliases: dict[str, str] | None = None) -> Episode:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    header = {}
    for key in ("EPISODE NUMBER", "EPISODE LOGLINE", "CONTINUITY NOTES"):
        m = re.search(rf"^{key}:\s*(.*)$", text, re.M)
        header[key] = m.group(1).strip() if m else ""
    m = re.search(r"(\d+)", header["EPISODE NUMBER"]) or re.search(r"episode-0*(\d+)", path.name, re.I)
    ep_no = int(m.group(1)) if m else 0

    body = text.split("--- SCRIPT START ---", 1)[-1].split("--- SCRIPT END ---", 1)[0]
    rows = body.splitlines()

    lines: list[Line] = []
    scene, heading = 0, ""
    i = 0
    while i < len(rows):
        row = rows[i].strip()
        sm = SCENE_RE.match(row)
        if sm:
            scene = int(sm.group(1))
            i += 1
            continue
        if row.lower().startswith("scene heading:"):
            heading = row.split(":", 1)[1].strip()
            i += 1
            continue
        bm = BLOCK_RE.match(row)
        if bm:
            name, tags = _split_head(bm.group("head"))
            start = end = None
            j = i + 1
            if j < len(rows):
                tm = TIME_RE.search(rows[j])
                if tm:
                    start, end = to_seconds(tm.group("s")), to_seconds(tm.group("e"))
                    j += 1
            body_lines = []
            while j < len(rows) and rows[j].strip() and not BLOCK_RE.match(rows[j].strip()) \
                    and not SCENE_RE.match(rows[j].strip()):
                body_lines.append(rows[j].strip())
                j += 1
            if start is not None:
                kind = _kind(name)
                lines.append(Line(
                    ep=ep_no, idx=len(lines), scene=scene, heading=heading, kind=kind,
                    speaker=canonical_speaker(name, aliases) if kind == "dialogue" else "",
                    raw_speaker=name if kind == "dialogue" else "",
                    tags=tags, start=start, end=max(end, start),
                    text=" ".join(body_lines).strip(),
                ))
            i = j
            continue
        i += 1

    scene_ends = [to_seconds(x) for x in re.findall(r"Scene end:\s*([\d:.]+)", body)]
    duration = max(scene_ends + [l.end for l in lines] + [0.0])
    return Episode(ep=ep_no, file=path.name, logline=header["EPISODE LOGLINE"],
                   continuity=header["CONTINUITY NOTES"], duration=duration, lines=lines)


def parse_folder(folder: str | Path, aliases: dict[str, str] | None = None) -> list[Episode]:
    files = sorted(Path(folder).rglob("*.txt"))
    eps = [parse_episode(f, aliases) for f in files]
    eps = [e for e in eps if e.lines]
    eps.sort(key=lambda e: e.ep)
    return eps


def render_lines(lines: list[Line], offset: float = 0.0, with_camera: bool = False) -> str:
    """Compact text form of lines for prompts: [mm:ss.cc-mm:ss.cc] KIND SPEAKER (tags): text"""
    out = []
    for l in lines:
        if l.kind == "camera" and not with_camera:
            continue
        who = {"dialogue": f"{l.speaker}" + (f" ({', '.join(l.tags)})" if l.tags else ""),
               "action": "ACTION", "sfx": "SFX", "camera": "CAMERA"}.get(l.kind, l.kind.upper())
        out.append(f"[{fmt_time(l.start - offset)}-{fmt_time(l.end - offset)}] {who}: {l.text}")
    return "\n".join(out)
