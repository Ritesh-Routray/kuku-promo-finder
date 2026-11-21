"""Build a static, no-server copy of the web app with a finished run baked in, ENCRYPTED with the access code.

The confidential results (script lines, promos) are stored only as AES-256-GCM ciphertext; the key is derived from
ACCESS_CODE with PBKDF2-SHA256 (600k iterations). The browser decrypts after the visitor enters the code.

Usage:
  python scripts/build_static.py --run outputs/kuku_full --out build/static [--publish rrgr8/promo-finder]
Needs ACCESS_CODE in .env (use a long random one: the ciphertext is public). --publish needs HF_TOKEN (write).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import promo_finder.config  # noqa: F401,E402  (loads .env)

from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # noqa: E402

ITER = 600_000
MAGIC = b"PF1"  # format: MAGIC | salt(16) | iv(12) | AES-GCM(gzip(payload))


def encrypt(data: bytes, code: str) -> bytes:
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(code.encode())
    return MAGIC + salt + iv + AESGCM(key).encrypt(iv, gzip.compress(data, 9), None)


def read(p: Path, name: str):
    f = p / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def bundle(run: Path, run_id: str) -> dict:
    log = read(run, "run_log.json") or {}
    hb = read(run, "heartbeats.json") or {}
    eps = read(run, "episodes.json") or []
    summary = {"id": run_id, "show": log.get("show", run_id), "episodes": log.get("episodes"),
               "ranked": log.get("ranked"), "started": log.get("started"), "models": log.get("models"),
               "protected": True, "status": "done"}
    curve = lambda e: hb.get(str(e["ep"]), {})  # noqa: E731
    return {
        "run": {**summary, "log": log},
        "promos": read(run, "promos_ranked.json") or [],
        "episodes": [{"ep": e["ep"], "logline": e["logline"], "duration": e["duration"], "n_lines": len(e["lines"]),
                      "curve": curve(e).get("curve", []), "peaks": curve(e).get("peaks", [])} for e in eps],
        "details": {str(e["ep"]): {**e, "curve": curve(e).get("curve", []), "peaks": curve(e).get("peaks", [])}
                    for e in eps},
    }


def export_zip(run: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(run.rglob("*")):
            if f.is_file() and f.name not in ("episodes.json", "contexts.json", "PROTECTED", "SHOWCASE", "feedback.json"):
                z.write(f, f.relative_to(run))
    return buf.getvalue()


SPACE_README = """---
title: Promo Finder
emoji: 🎬
colorFrom: red
colorTo: gray
sdk: static
app_file: index.html
pinned: false
---

Promo Finder: finds 20–60 s promos in microdrama screenplays (hook in 3 s, cliffhanger ending, makes sense alone).
The demo show's results are encrypted; enter the access code from the submission to view them.
Live analysis of a new show runs from the code repository (see its README).
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="outputs/kuku_full")
    ap.add_argument("--out", default="build/static")
    ap.add_argument("--id", default="kuku_demo")
    ap.add_argument("--publish", help="username/space-name to upload to (static Space)")
    a = ap.parse_args()
    code = os.getenv("ACCESS_CODE", "")
    if len(code) < 16:
        sys.exit("Set a long random ACCESS_CODE (16+ chars) in .env: the encrypted file is public.")
    run, out = ROOT / a.run, ROOT / a.out
    if not (run / "run_log.json").exists():
        sys.exit(f"{run} is not a finished run")

    web = ROOT / "web"
    env = {**os.environ, "VITE_STATIC": "1"}
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "run", "build", "--", "--outDir", str(out), "--emptyOutDir"], cwd=web, env=env, check=True)

    b = bundle(run, a.id)
    (out / "data.enc").write_bytes(encrypt(json.dumps(b, ensure_ascii=False).encode("utf-8"), code))
    (out / "export.enc").write_bytes(encrypt(export_zip(run), code))
    # Public, non-confidential stub so the app can list the run before it is unlocked.
    (out / "meta.json").write_text(json.dumps({"id": a.id, "show": "Kuku demo show", "protected": True,
                                               "episodes": b["run"]["episodes"], "ranked": b["run"]["ranked"]}),
                                   encoding="utf-8")
    (out / "README.md").write_text(SPACE_README, encoding="utf-8")
    leaks = [f for f in out.rglob("*") if f.is_file() and f.suffix in (".txt", ".json") and f.name != "meta.json"]
    if leaks:
        sys.exit(f"Refusing: plaintext data files in build: {leaks}")
    print(f"Built {out}  ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) // 1024} KB)")

    if a.publish:
        from huggingface_hub import HfApi
        api = HfApi(token=os.getenv("HF_TOKEN"))
        api.create_repo(a.publish, repo_type="space", space_sdk="static", private=False, exist_ok=True)
        api.upload_folder(folder_path=str(out), repo_id=a.publish, repo_type="space",
                          commit_message="Publish static Promo Finder", delete_patterns=["*"])
        print(f"Live at https://huggingface.co/spaces/{a.publish}")


if __name__ == "__main__":
    main()
