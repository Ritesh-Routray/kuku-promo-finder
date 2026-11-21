"""Create/update the Hugging Face Space and set its secrets, without git.

Uploads ONLY an allowlist of code files (never data/, outputs/, .env or the scripts).

Usage:
  python scripts/deploy_space.py --space <username>/promo-finder --dataset <username>/kuku-promo-demo
Needs HF_TOKEN (write token) in .env. Space secrets are read from .env:
  GEMINI_API_KEY, GROQ_API_KEY, ACCESS_CODE, and HF_SPACE_TOKEN (read token; falls back to HF_TOKEN).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import promo_finder.config  # noqa: F401,E402  (loads .env)

from huggingface_hub import HfApi  # noqa: E402

ALLOW = ["Dockerfile", "README.md", "config.yaml", "requirements.txt", ".dockerignore",
         "promo_finder/**", "server/**", "web/src/**", "web/index.html", "web/package.json",
         "web/package-lock.json", "web/tsconfig.json", "web/vite.config.ts"]
IGNORE = ["**/__pycache__/**", "**/*.pyc", "server/runs.db", "**/.env", "**/*.txt.bak"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="username/space-name")
    ap.add_argument("--dataset", required=True, help="username/dataset-name holding the private demo run")
    ap.add_argument("--dry-run", action="store_true", help="only list the files that would be uploaded")
    a = ap.parse_args()

    import fnmatch
    files = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*") if p.is_file())
    keep = [f for f in files if any(fnmatch.fnmatch(f, g) for g in ALLOW)
            and not any(fnmatch.fnmatch(f, g) for g in IGNORE)]
    bad = [f for f in keep if f.endswith(".txt") and f != "requirements.txt"]
    if bad:
        sys.exit(f"Refusing: .txt files in upload set (possible scripts): {bad}")
    print(f"{len(keep)} files to upload")
    if a.dry_run:
        print("\n".join(keep))
        return

    token = os.getenv("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (write token) in .env first.")
    api = HfApi(token=token)
    api.create_repo(a.space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)

    secrets = {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "ACCESS_CODE": os.getenv("ACCESS_CODE"),
        "HF_TOKEN": os.getenv("HF_SPACE_TOKEN") or token,
    }
    for k, v in secrets.items():
        if v:
            api.add_space_secret(a.space, k, v)
            print(f"secret set: {k}")
        else:
            print(f"secret SKIPPED (empty in .env): {k}")
    api.add_space_variable(a.space, "DEMO_DATASET", a.dataset)

    api.upload_folder(folder_path=str(ROOT), repo_id=a.space, repo_type="space",
                      allow_patterns=keep, commit_message="Deploy Promo Finder")
    print(f"Uploaded. Build log: https://huggingface.co/spaces/{a.space}?logs=build")


if __name__ == "__main__":
    main()
