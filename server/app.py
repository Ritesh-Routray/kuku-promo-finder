"""FastAPI backend: runs the pipeline as background jobs, streams progress, serves results and the React app."""
from __future__ import annotations

import asyncio
import io
import json
import os
import queue
import shutil
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from promo_finder.config import ROOT, load_config
from promo_finder.pipeline import run as run_pipeline

RUNS = ROOT / "outputs"
DEMO = ROOT / "data" / "demo"
UPLOADS = ROOT / "data" / "uploads"
for d in (RUNS, DEMO, UPLOADS):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Kuku Promo Finder")
JOBS: dict[str, dict] = {}
WORK: "queue.Queue[tuple]" = queue.Queue()


# ---------- demo data (private HF dataset, pulled at startup) ----------
def _pull_demo() -> None:
    repo, token = os.getenv("DEMO_DATASET"), os.getenv("HF_TOKEN")
    if not (repo and token):
        return
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=repo, repo_type="dataset", local_dir=str(DEMO), token=token)
    except Exception as e:  # the app still works without the demo
        print("demo download failed:", e)


# ---------- helpers ----------
def _run_dir(run_id: str) -> Path:
    for base in (RUNS, DEMO):
        p = base / run_id
        if p.is_dir() and (p / "run_log.json").exists():
            return p
    raise HTTPException(404, "run not found")


def _protected(p: Path) -> bool:
    return p.parent == DEMO or (p / "PROTECTED").exists()


def _check(p: Path, code: str | None) -> None:
    if _protected(p) and (not os.getenv("ACCESS_CODE") or code != os.getenv("ACCESS_CODE")):
        raise HTTPException(403, "access code required")


def _read(p: Path, name: str):
    f = p / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _summary(p: Path) -> dict:
    log = _read(p, "run_log.json") or {}
    return {"id": p.name, "show": log.get("show", p.name), "episodes": log.get("episodes"),
            "ranked": log.get("ranked"), "started": log.get("started"), "models": log.get("models"),
            "protected": _protected(p), "status": "done"}


# ---------- worker ----------
def _worker() -> None:
    while True:
        run_id, input_dir, cfg, keys, show, limit = WORK.get()
        job = JOBS[run_id]
        job["status"] = "running"

        def progress(stage, pct, msg):
            job["events"].append({"stage": stage, "pct": round(pct, 1), "msg": msg,
                                  "t": datetime.now().isoformat(timespec="seconds")})
        try:
            run_pipeline(input_dir, RUNS / run_id, cfg, show=show, api_keys=keys, progress=progress,
                         episodes_limit=limit)
            job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            job["events"].append({"stage": "error", "pct": 100, "msg": str(e)[:500]})
        finally:
            shutil.rmtree(input_dir, ignore_errors=True)  # never keep uploaded scripts


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_pull_demo, daemon=True).start()
    threading.Thread(target=_worker, daemon=True).start()


# ---------- API ----------
@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def config():
    cfg = load_config()
    return {"models": cfg["models"], "promo": cfg["promo"],
            "suggested": {"generator": ["gemini/gemini-3.5-flash-lite", "gemini/gemini-3.5-flash", "groq/openai/gpt-oss-120b", "groq/qwen/qwen3.8-27b", "heuristic"],
                          "judge": ["groq/openai/gpt-oss-120b", "groq/qwen/qwen3.8-27b", "gemini/gemini-3.5-flash-lite", "heuristic"]},
            "server_keys": {"gemini": bool(os.getenv("GEMINI_API_KEY")), "groq": bool(os.getenv("GROQ_API_KEY"))},
            "demo_available": any((p / "run_log.json").exists() for p in DEMO.iterdir() if p.is_dir())}


@app.get("/api/runs")
def list_runs(x_access_code: str | None = Header(None)):
    """Lists demo/showcase runs only. Uploaded runs are unlisted and opened by their id."""
    out = []
    for base in (DEMO, RUNS):
        for p in sorted(base.iterdir(), reverse=True):
            if p.is_dir() and (p / "run_log.json").exists() and ((p / "SHOWCASE").exists() or base == DEMO):
                out.append(_summary(p))
    return out


@app.post("/api/runs")
async def create_run(files: list[UploadFile] = File(...), show: str = Form(""), generator: str = Form(""),
                     judge: str = Form(""), gemini_key: str = Form(""), groq_key: str = Form(""),
                     limit: int = Form(0)):
    run_id = uuid.uuid4().hex[:12]
    tmp = UPLOADS / run_id
    tmp.mkdir(parents=True)
    n = 0
    for f in files:
        data = await f.read()
        if f.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for m in z.infolist():
                    if m.filename.lower().endswith(".txt") and not m.is_dir() and ".." not in m.filename:
                        (tmp / Path(m.filename).name).write_bytes(z.read(m))
                        n += 1
        elif f.filename.lower().endswith(".txt"):
            (tmp / Path(f.filename).name).write_bytes(data)
            n += 1
    if n == 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(400, "Upload a .zip of screenplay .txt files or the .txt files themselves.")
    models = {k: v for k, v in {"generator": generator, "judge": judge}.items() if v}
    cfg = load_config(overrides={"models": models})
    JOBS[run_id] = {"status": "queued", "events": [{"stage": "queued", "pct": 0, "msg": f"{n} files received"}],
                    "show": show or "Uploaded show"}
    WORK.put((run_id, tmp, cfg, {"gemini": gemini_key, "groq": groq_key}, show or None, limit or None))
    return {"id": run_id}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str):
    if run_id not in JOBS:
        raise HTTPException(404, "no live job")

    async def gen():
        i = 0
        while True:
            job = JOBS[run_id]
            while i < len(job["events"]):
                yield {"event": "progress", "data": json.dumps(job["events"][i])}
                i += 1
            if job["status"] in ("done", "error"):
                yield {"event": "end", "data": json.dumps({"status": job["status"]})}
                return
            await asyncio.sleep(0.7)
    return EventSourceResponse(gen())


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, x_access_code: str | None = Header(None)):
    if run_id in JOBS and JOBS[run_id]["status"] != "done":
        return {"id": run_id, "status": JOBS[run_id]["status"], "events": JOBS[run_id]["events"]}
    p = _run_dir(run_id)
    _check(p, x_access_code)
    return {**_summary(p), "log": _read(p, "run_log.json")}


@app.get("/api/runs/{run_id}/promos")
def promos(run_id: str, x_access_code: str | None = Header(None)):
    p = _run_dir(run_id)
    _check(p, x_access_code)
    fb = _read(p, "feedback.json") or {}
    return [{**x, "feedback": fb.get(x["id"])} for x in _read(p, "promos_ranked.json") or []]


@app.get("/api/runs/{run_id}/episodes")
def episodes(run_id: str, x_access_code: str | None = Header(None)):
    p = _run_dir(run_id)
    _check(p, x_access_code)
    hb = _read(p, "heartbeats.json") or {}
    return [{**{k: e[k] for k in ("ep", "logline", "duration")}, "n_lines": len(e["lines"]),
             "curve": hb.get(str(e["ep"]), {}).get("curve", []), "peaks": hb.get(str(e["ep"]), {}).get("peaks", [])}
            for e in _read(p, "episodes.json") or []]


@app.get("/api/runs/{run_id}/episodes/{ep}")
def episode(run_id: str, ep: int, x_access_code: str | None = Header(None)):
    p = _run_dir(run_id)
    _check(p, x_access_code)
    for e in _read(p, "episodes.json") or []:
        if e["ep"] == ep:
            hb = (_read(p, "heartbeats.json") or {}).get(str(ep), {})
            return {**e, "curve": hb.get("curve", []), "peaks": hb.get("peaks", [])}
    raise HTTPException(404, "episode not found")


class Feedback(BaseModel):
    verdict: str  # accept | reject | adjust
    note: str = ""


@app.post("/api/runs/{run_id}/promos/{pid}/feedback")
def feedback(run_id: str, pid: str, fb: Feedback, x_access_code: str | None = Header(None)):
    p = _run_dir(run_id)
    _check(p, x_access_code)
    data = _read(p, "feedback.json") or {}
    data[pid] = {**fb.model_dump(), "at": datetime.now().isoformat(timespec="seconds")}
    (p / "feedback.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data[pid]


@app.get("/api/runs/{run_id}/export")
def export(run_id: str, x_access_code: str | None = Header(None), code: str | None = None):
    p = _run_dir(run_id)
    _check(p, x_access_code or code)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in p.rglob("*"):
            if f.is_file() and f.name not in ("episodes.json", "contexts.json", "PROTECTED", "SHOWCASE"):
                z.write(f, f.relative_to(p))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="promos_{run_id}.zip"'})


# ---------- React app ----------
DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
