"""Tests that need no API keys. The Kuku scripts are read from KUKU_SCRIPTS if set (they are not in the repo)."""
import os
import re
from pathlib import Path

import pytest

from promo_finder.config import load_config
from promo_finder.parse import parse_episode, parse_folder, to_seconds, canonical_speaker
from promo_finder.snap import Snapper, tiou

SAMPLE = """EPISODE NUMBER: Episode 7
EPISODE LOGLINE: A test.
CONTINUITY NOTES: None.

--- SCRIPT START ---

SCENE 01
Scene heading: INT. HALL – DAY
Scene start: 00:00.00
Scene end: 01:10.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:02.00)
Wide shot of the hall.

**LADY ANNA (Cold, Furious):**
Start: (00:02.50) | End: (00:04.00)
"You lied to me!"

**ACTION:**
Start: (00:04.00) | End: (00:05.00)
She slaps him.

**TOM (Stunned):**
Start: (00:30.00) | End: (00:33.00)
"Then who is the father?"

**SOUND FX:**
Start: (01:05.00) | End: (01:10.00)
Ominous sting.

--- SCRIPT END ---
"""


@pytest.fixture
def ep(tmp_path):
    f = tmp_path / "episode-007.txt"
    f.write_text(SAMPLE, encoding="utf-8")
    return parse_episode(f)


def test_time():
    assert to_seconds("01:02.50") == 62.5
    assert to_seconds("1:00:00.0") == 3600


def test_speaker_alias():
    assert canonical_speaker("LADY ELEANOR") == "ELEANOR"
    assert canonical_speaker("LADY IN GOLD GOWN") == "LADY IN GOLD GOWN"


def test_parse_sample(ep):
    assert ep.ep == 7 and ep.duration == 70.0
    assert [l.kind for l in ep.lines] == ["camera", "dialogue", "action", "dialogue", "sfx"]
    assert ep.lines[1].speaker == "ANNA" and ep.lines[1].tags == ["Cold", "Furious"]


def test_snap_moves_start_to_hook_and_end_to_cliff(ep):
    cfg = load_config()
    clip, why = Snapper(ep, cfg).build({"segments": [{"start": "00:00.00", "end": "00:40.00"}],
                                        "hook_line": "You lied to me!", "cliffhanger_line": "Then who is the father?"})
    assert clip is not None, why
    # hook at 2.5s is inside the 3s window, so the start is kept; the end moves onto the cliffhanger
    assert clip["hook_at"] == 2.5
    assert clip["segments"][0]["end"] == 33.0
    assert cfg["promo"]["min_sec"] <= clip["duration"] <= cfg["promo"]["max_sec"]


def test_snap_rejects_too_long(ep):
    cfg = load_config()
    clip, why = Snapper(ep, cfg).build({"segments": [{"start": "00:02.50", "end": "01:10.00"}],
                                        "hook_line": "You lied", "cliffhanger_line": "Ominous sting."})
    assert clip is None and "too long" in why


def test_tiou():
    a = {"segments": [{"ep": 1, "start": 0, "end": 10}]}
    b = {"segments": [{"ep": 1, "start": 5, "end": 15}]}
    assert abs(tiou(a, b) - 1 / 3) < 1e-6


@pytest.mark.skipif(not os.getenv("KUKU_SCRIPTS"), reason="set KUKU_SCRIPTS to the scripts folder")
def test_parse_all_kuku_blocks():
    folder = Path(os.environ["KUKU_SCRIPTS"])
    eps = parse_folder(folder)
    assert len(eps) == 50
    for e in eps:
        raw = next(folder.rglob(e.file)).read_text(encoding="utf-8")
        assert len(re.findall(r"^\*\*.+\*\*\s*$", raw, re.M)) == len(e.lines)
        assert all(l.end >= l.start for l in e.lines)


def test_short_clip_grows_into_setup_not_past_cliffhanger(ep):
    """A clip that is too short gets its start pulled earlier (hook stays within 3 s), never its end past the cliffhanger."""
    cfg = load_config()
    cfg["promo"]["min_sec"] = 5.0
    clip, why = Snapper(ep, cfg).build({"segments": [{"start": "00:02.50", "end": "00:05.00"}],
                                        "hook_line": "You lied to me!", "cliffhanger_line": "She slaps him."})
    assert clip is not None, why
    assert clip["segments"][0]["end"] == 5.0          # still ends on the cliffhanger line
    assert clip["segments"][0]["start"] == 0.0        # grew backwards; hook (2.5 s) is still within 3 s
    assert clip["hook_at"] <= cfg["promo"]["hook_within_sec"]
    assert "start moved earlier into the setup" in clip["flags"]


def test_short_clip_rejected_rather_than_stretched(ep):
    cfg = load_config()
    clip, why = Snapper(ep, cfg).build({"segments": [{"start": "00:30.00", "end": "00:33.00"}],
                                        "hook_line": "Then who is the father?", "cliffhanger_line": "Then who is the father?"})
    assert clip is None and "too short" in why
