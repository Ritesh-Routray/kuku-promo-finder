from __future__ import annotations

import copy
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    cfg = yaml.safe_load(Path(path or ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg = _merge(cfg, overrides or {})
    cache = Path(cfg.get("cache_dir", ".cache"))
    cfg["cache_dir"] = str(cache if cache.is_absolute() else ROOT / cache)
    return cfg
