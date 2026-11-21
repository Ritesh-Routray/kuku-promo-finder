"""Upload a finished run to a PRIVATE Hugging Face dataset so the deployed Space can show it behind an access code.

Usage:
  python scripts/publish_demo.py --run outputs/kuku_full --repo <your-hf-username>/kuku-promo-demo
Needs HF_TOKEN (a write token) in .env or the environment. The dataset is created private.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import promo_finder.config  # noqa: F401,E402  (loads .env)

from huggingface_hub import HfApi  # noqa: E402

SKIP = {"contexts.json", "SHOWCASE", "PROTECTED", "feedback.json"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--repo", required=True, help="username/dataset-name")
    ap.add_argument("--name", default="kuku_demo", help="folder name inside the dataset (= run id in the app)")
    a = ap.parse_args()
    token = os.getenv("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (write token) in .env first.")
    run = Path(a.run)
    if not (run / "run_log.json").exists():
        sys.exit(f"{run} is not a finished run")
    api = HfApi(token=token)
    api.create_repo(a.repo, repo_type="dataset", private=True, exist_ok=True)
    info = api.repo_info(a.repo, repo_type="dataset")
    if not info.private:
        sys.exit(f"{a.repo} exists and is PUBLIC. Refusing to upload confidential content.")
    api.upload_folder(folder_path=str(run), path_in_repo=a.name, repo_id=a.repo, repo_type="dataset",
                      ignore_patterns=list(SKIP) + ["edl/*.tmp"])
    print(f"Uploaded {run} -> {a.repo}/{a.name} (private). Set DEMO_DATASET={a.repo} in the Space secrets.")


if __name__ == "__main__":
    main()
