"""Local, free models that score every line. They rank moments; they never pick clip boundaries."""
from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path

import numpy as np

from .parse import Episode

EMOTIONS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]


def _device() -> int:
    try:
        import torch
        return 0 if torch.cuda.is_available() else -1
    except Exception:
        return -1


@functools.lru_cache(maxsize=2)
def _emotion_model(model_name: str):
    # Load the model directly (not transformers.pipeline) to avoid pulling in vision deps.
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).eval()
    dev = "cuda" if _device() == 0 else "cpu"
    return tok, model.to(dev), dev


def _classify(texts: list[str], model_name: str, batch: int = 32) -> list[dict]:
    import torch
    tok, model, dev = _emotion_model(model_name)
    labels = [model.config.id2label[i] for i in range(model.config.num_labels)]
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i + batch], padding=True, truncation=True, max_length=128, return_tensors="pt").to(dev)
            probs = torch.softmax(model(**enc).logits, dim=-1).cpu().numpy()
            out += [{labels[j]: round(float(p[j]), 4) for j in range(len(labels))} for p in probs]
    return out


@functools.lru_cache(maxsize=2)
def embedder(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, device="cuda" if _device() == 0 else "cpu")


def embed(texts: list[str], model_name: str) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    return np.asarray(embedder(model_name).encode(texts, batch_size=64, normalize_embeddings=True,
                                                   show_progress_bar=False), dtype=np.float32)


def emotion_scores(episodes: list[Episode], model_name: str, cache_dir: str | Path) -> dict[tuple[int, int], dict]:
    """Emotion probabilities for every dialogue line, cached on disk by content hash."""
    items = [(e.ep, l.idx, l.text.strip('"')) for e in episodes for l in e.lines if l.kind == "dialogue" and l.text]
    key = hashlib.sha256((model_name + json.dumps(items)).encode()).hexdigest()[:16]
    cache = Path(cache_dir) / f"emotion_{key}.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return {(int(k.split(":")[0]), int(k.split(":")[1])): v for k, v in raw.items()}
    out: dict[tuple[int, int], dict] = {}
    if items:
        preds = _classify([t for _, _, t in items], model_name)
        for (ep, idx, _), p in zip(items, preds):
            out[(ep, idx)] = p
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({f"{k[0]}:{k[1]}": v for k, v in out.items()}), encoding="utf-8")
    return out
