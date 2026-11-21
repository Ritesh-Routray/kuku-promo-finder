"""One wrapper for every LLM call: model swap via config, JSON validation, disk cache, rate limits, usage log."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from string import Template
from pathlib import Path
from typing import Any

from diskcache import Cache
from pydantic import BaseModel, ValidationError

PROMPTS = Path(__file__).parent / "prompts"
KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY",
           "anthropic": "ANTHROPIC_API_KEY"}


def prompt(name: str, **kw: Any) -> str:
    return Template((PROMPTS / f"{name}.md").read_text(encoding="utf-8")).safe_substitute(**kw)


def _extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, cfg: dict, api_keys: dict | None = None):
        self.cfg = cfg
        self.keys = {k: v for k, v in (api_keys or {}).items() if v}
        self.cache = Cache(str(Path(cfg["cache_dir"]) / "llm"))
        self.usage: list[dict] = []
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self.exhausted: set[str] = set()
        self.events: list[str] = []

    def model_for(self, role: str) -> str:
        return self.cfg["models"][role]

    def is_heuristic(self, role: str) -> bool:
        return self.model_for(role) == "heuristic"

    @staticmethod
    def provider(model: str) -> str:
        return model.split("/", 1)[0] if "/" in model else "openai"

    def _api_key(self, model: str) -> str | None:
        p = self.provider(model)
        return self.keys.get(p) or os.getenv(KEY_ENV.get(p, ""), None)

    def _throttle(self, model: str) -> None:
        p = self.provider(model)
        rpm = self.cfg.get("rate_limits_rpm", {}).get(p) or self.cfg.get("rate_limits_rpm", {}).get("default", 20)
        gap = 60.0 / rpm
        with self._lock:
            wait = self._last.get(p, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last[p] = time.time()

    def _call(self, model: str, messages: list[dict], temperature: float) -> tuple[str, dict]:
        import litellm
        litellm.suppress_debug_info = True
        litellm.drop_params = True  # some newer models reject temperature etc.
        kwargs = dict(model=model, messages=messages, temperature=temperature,
                      reasoning_effort=self.cfg["models"].get("reasoning_effort"),
                      response_format={"type": "json_object"}, timeout=120)
        key = self._api_key(model)
        if key:
            kwargs["api_key"] = key
        self._throttle(model)
        t0 = time.time()
        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content or ""
        u = getattr(resp, "usage", None)
        try:
            cost = float(litellm.completion_cost(completion_response=resp))
        except Exception:
            cost = 0.0
        meta = {"model": model, "latency_s": round(time.time() - t0, 2),
                "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                "cost_usd_at_list_price": round(cost, 6)}
        return text, meta

    def json(self, role: str, system: str, user: str, schema: type[BaseModel] | None = None,
             temperature: float | None = None, tag: str = "") -> dict:
        """Call the model for `role`, return parsed (and validated) JSON. Cached by model+prompt."""
        temperature = self.cfg["models"].get("temperature", 0.4) if temperature is None else temperature
        models = [self.model_for(role)]
        fbs = self.cfg["models"].get(f"{role}_fallbacks") or self.cfg["models"].get("fallbacks") \
            or [self.cfg["models"].get("fallback")]
        for fb in fbs:
            if fb and fb != "heuristic" and fb not in models:
                models.append(fb)
        base = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err: Exception | None = None
        keys = {m: hashlib.sha256(json.dumps([m, base, temperature]).encode()).hexdigest() for m in models}
        for m in models:  # any model's cached answer wins: reruns are free
            if keys[m] in self.cache:
                self.usage.append({"model": m, "tag": tag, "cached": True})
                return self.cache[keys[m]]
        dead: set[str] = set()
        for rnd in range(4):
            live = [m for m in models if m not in self.exhausted and m not in dead]
            if not live:
                break
            for model in live:
                messages = list(base)
                for _ in range(2):  # one retry for invalid JSON
                    try:
                        text, meta = self._call(model, messages, temperature)
                        data = _extract_json(text)
                        if schema is not None:
                            data = schema.model_validate(data).model_dump()
                        self.cache[keys[model]] = data
                        self.usage.append({**meta, "tag": tag, "cached": False})
                        return data
                    except (ValidationError, json.JSONDecodeError) as e:
                        last_err = e
                        messages = base + [{"role": "user", "content":
                            f"Your previous reply was not valid JSON for the schema ({str(e)[:300]}). Reply again with only valid JSON."}]
                    except Exception as e:  # rate limits, timeouts, provider errors
                        last_err = e
                        msg = str(e).lower()
                        if any(s in msg for s in ("api key", "authentication", "permission", "not found",
                                                  "invalid model", "does not exist", "bad request", "badrequest")):
                            dead.add(model)
                        elif "per day" in msg or "free_tier_requests" in msg or "exceeded your current quota" in msg:
                            self.exhausted.add(model)  # daily quota gone for this run
                            self.events.append(f"{model} daily quota exhausted; using fallbacks")
                        # per-minute rate limit / timeout: move straight on to the next model (separate quota)
                        break
            if rnd < 3:
                time.sleep(15 * (rnd + 1))  # every model was busy: wait for per-minute limits to reset
        raise LLMError(f"{role} call failed on {models}: {last_err}")

    def summary(self) -> dict:
        live = [u for u in self.usage if not u.get("cached")]
        by_model: dict[str, dict] = {}
        for u in live:
            m = by_model.setdefault(u["model"], {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                                 "cost_usd_at_list_price": 0.0, "latency_s": 0.0})
            m["calls"] += 1
            for k in ("prompt_tokens", "completion_tokens", "cost_usd_at_list_price", "latency_s"):
                m[k] = round(m[k] + u.get(k, 0), 6)
        calls_by_tag_model: dict[str, int] = {}
        for u in self.usage:
            k = f"{u['tag'].split('_')[0]}:{u['model']}"
            calls_by_tag_model[k] = calls_by_tag_model.get(k, 0) + 1
        return {"live_calls": len(live), "cached_calls": len(self.usage) - len(live), "by_model": by_model,
                "served_by": calls_by_tag_model, "events": self.events}
