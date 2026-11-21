"""Record a silent walkthrough of the web app (for the submission video). The narrator adds voice later.

Usage: python scripts/record_demo.py --url http://localhost:8090/ --out media/promo_finder_demo.mp4
Uses the installed Microsoft Edge through Playwright; the access code is set in the page's session storage
(never typed on screen, so it never appears in the video).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import promo_finder.config  # noqa: F401,E402  (loads .env)

from playwright.sync_api import sync_playwright  # noqa: E402

W, H = 1440, 900

# A visible cursor dot (recorded videos have no mouse pointer) that follows the mouse and pulses on click.
CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('__cur')) return;
    const d = document.createElement('div'); d.id = '__cur';
    Object.assign(d.style, {position:'fixed', left:'0', top:'0', width:'22px', height:'22px', marginLeft:'-11px', marginTop:'-11px',
      borderRadius:'50%', background:'rgba(255,255,255,.28)', border:'2px solid rgba(255,255,255,.9)', zIndex:'99999',
      pointerEvents:'none', transition:'transform .12s, left .05s linear, top .05s linear', boxShadow:'0 2px 10px rgba(0,0,0,.5)'});
    document.body.appendChild(d);
    addEventListener('mousemove', e => { d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => d.style.transform = 'scale(.7)', true);
    addEventListener('mouseup', () => d.style.transform = 'scale(1)', true);
  };
  if (document.body) add(); else addEventListener('DOMContentLoaded', add);
})();
"""


class Tour:
    def __init__(self, page):
        self.page = page
        self.x, self.y = W / 2, H / 2
        self.t0 = time.time()
        self.marks: list[tuple[float, str]] = []

    def mark(self, label: str):
        self.marks.append((time.time() - self.t0, label))

    def wait(self, s: float):
        self.page.wait_for_timeout(int(s * 1000))

    def move(self, x: float, y: float, steps: int = 25):
        self.page.mouse.move(x, y, steps=steps)
        self.x, self.y = x, y

    def click_el(self, locator, pause: float = 0.6):
        locator.scroll_into_view_if_needed()
        b = locator.bounding_box()
        self.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        self.wait(0.35)
        self.page.mouse.down(); self.page.mouse.up()
        self.wait(pause)

    def scroll(self, total: int, step: int = 60, delay: float = 0.03):
        for _ in range(abs(total) // step):
            self.page.mouse.wheel(0, step if total > 0 else -step)
            self.wait(delay)

    def go(self, hash_: str, pause: float = 1.5):
        self.page.evaluate(f"location.hash = '{hash_}'")
        self.wait(pause)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8090/")
    ap.add_argument("--out", default="media/promo_finder_demo.mp4")
    a = ap.parse_args()
    code = os.getenv("ACCESS_CODE", "")
    out = ROOT / a.out
    raw_dir = out.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                  record_video_dir=str(raw_dir), record_video_size={"width": W, "height": H},
                                  color_scheme="dark")
        ctx.add_init_script(f"try{{sessionStorage.setItem('pf_access_code', {code!r})}}catch(e){{}}")
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        t = Tour(page)
        page.goto(a.url, wait_until="networkidle")
        page.wait_for_selector(".tile", timeout=60000)

        # 1. Discover board
        t.mark("Discover: headline and stats")
        t.move(700, 300); t.wait(4)
        t.move(760, 470); t.wait(2.5)
        t.mark("Story-type filters")
        t.scroll(420); t.wait(1.2)
        chips = page.locator(".chip")
        t.click_el(chips.nth(2), 2.2)
        t.click_el(chips.nth(0), 1.5)
        t.mark("Post these first: ranked posters")
        t.scroll(360); t.wait(3)
        t.scroll(700); t.wait(2)
        t.mark("More promos list")
        t.scroll(900, delay=0.02); t.wait(2)
        t.scroll(-2600, step=120, delay=0.01); t.wait(1)

        # 2. Player on the #2 promo
        t.mark("Open a promo: timed script player")
        t.scroll(380); t.wait(0.8)
        t.click_el(page.locator(".tile").nth(1), 2.5)
        t.click_el(page.locator(".play-big"), 0.2)
        t.mark("Playing: script plays in real time, amber = first 3 seconds")
        t.move(1000, 330); t.wait(16)
        t.click_el(page.locator(".play-big"), 1)
        t.mark("Why it works: hook, cliffhanger, score per signal")
        t.scroll(500); t.wait(4)
        t.scroll(300); t.wait(3)
        t.mark("Judges tab: 3-second test, cold viewer, guesses vs. what really happens")
        t.click_el(page.locator(".tab", has_text="Judges"), 3)
        t.scroll(400); t.wait(5)
        t.mark("Segments & export: exact timestamps, EDL/CSV download")
        t.click_el(page.locator(".tab", has_text="Segments"), 4)

        # 3. A flagged pick (honest failure)
        t.mark("A flagged pick: why it needs a human look")
        t.go("#/promo/e011_1", 2)
        t.scroll(600); t.wait(1)
        t.click_el(page.locator(".tab", has_text="Why it works"), 1)
        t.scroll(400); t.wait(5)

        # 4. Episodes and heartbeat
        t.mark("Episodes: drama heartbeat per episode")
        t.go("#/episodes", 2)
        t.move(1100, 400); t.wait(2)
        t.scroll(600); t.wait(1.5)
        t.scroll(-600); t.wait(0.5)
        t.click_el(page.locator(".list-row").nth(1), 2.5)
        t.mark("Episode heartbeat: peaks, chosen promo ranges, click to jump")
        svg = page.locator(".hb svg").first
        b = svg.bounding_box()
        t.move(b["x"] + b["width"] * 0.1, b["y"] + b["height"] * 0.5); t.wait(1)
        t.move(b["x"] + b["width"] * 0.62, b["y"] + b["height"] * 0.4, steps=60); t.wait(0.5)
        page.mouse.down(); page.mouse.up(); t.wait(3)
        t.scroll(500); t.wait(3)

        # 5. How it works + run locally
        t.mark("How it works")
        t.go("#/about", 2)
        t.move(700, 450); t.wait(2); t.scroll(500); t.wait(4)
        t.mark("Analyze a new show (run from the repo)")
        t.go("#/analyze", 5)
        t.mark("End: back to Discover")
        t.go("#/", 3)

        video = page.video
        ctx.close(); browser.close()
        webm = Path(video.path())

    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "slow", "-crf", "18", "-movflags", "+faststart", str(out)], check=True)
    webm.unlink(missing_ok=True)
    (out.with_suffix(".timestamps.txt")).write_text(
        "\n".join(f"{int(s // 60)}:{s % 60:05.2f}  {lbl}" for s, lbl in t.marks), encoding="utf-8")
    print(f"Saved {out} and {out.with_suffix('.timestamps.txt')}")


if __name__ == "__main__":
    main()
