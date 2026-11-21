"""Light story memory (RAG): 'previously on' from script headers + similarity search over earlier scenes."""
from __future__ import annotations

import numpy as np

from .parse import Episode
from .signals import embed


class StoryMemory:
    def __init__(self, episodes: list[Episode], embed_model: str):
        self.episodes = {e.ep: e for e in episodes}
        self.embed_model = embed_model
        self.docs: list[dict] = []
        for e in episodes:
            scenes: dict[int, list] = {}
            for l in e.lines:
                if l.kind in ("dialogue", "action"):
                    scenes.setdefault(l.scene, []).append(l)
            for sc, ls in scenes.items():
                text = " ".join((f"{l.speaker}: {l.text}" if l.speaker else l.text) for l in ls)
                self.docs.append({"ep": e.ep, "scene": sc, "heading": ls[0].heading,
                                  "start": ls[0].start, "text": text[:700]})
        self.vecs = embed([f"{d['heading']}. {d['text']}" for d in self.docs], embed_model)

    def previously(self, ep: int, n: int = 3) -> str:
        prev = [self.episodes[k] for k in sorted(self.episodes) if ep - n <= k < ep]
        cur = self.episodes.get(ep)
        parts = [f"Ep {p.ep}: {p.logline}" for p in prev]
        if cur and cur.continuity:
            parts.append(f"Continuity for this episode: {cur.continuity}")
        return "\n".join(parts) or "(This is the first episode.)"

    def related(self, ep: int, query: str, k: int = 3) -> list[dict]:
        if not self.docs:
            return []
        q = embed([query], self.embed_model)[0]
        sims = self.vecs @ q
        idx = [i for i in np.argsort(-sims) if self.docs[i]["ep"] < ep][:k]
        return [{**self.docs[i], "sim": round(float(sims[i]), 3)} for i in idx]

    @staticmethod
    def format_related(docs: list[dict]) -> str:
        if not docs:
            return "(none)"
        return "\n".join(f"- Ep {d['ep']} scene {d['scene']} ({d['heading']}): {d['text'][:400]}" for d in docs)
