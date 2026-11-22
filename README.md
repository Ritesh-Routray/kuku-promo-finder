# Promo Finder

Finds the best **20–60 second promo clips** in microdrama screenplays: a hook in the first 3 seconds,
a cliffhanger at the end, and a clip that makes sense to someone who has never seen the show.

For every promo it gives the episode, the start and end of each segment, the hook line, the cliffhanger
line, why it works, and a rank. Picks that need a human look are flagged.

**Live demo:** https://rrgr8-promo-finder.static.hf.space (the demo show is confidential; the access code is in the submission)

Built by Ritesh Routray for Kuku FM's AI Generalist assignment (Problem 1: Find the Promos).

## How it works

1. **Read** the screenplays: every line, action, camera shot and sound cue with its timestamp.
2. **Drama heartbeat**: a small local emotion model plus the script's own emotion tags, event words, sound cues and camera cuts give an intensity score for every second. The peaks are likely promo moments.
3. **Story memory**: the AI gets a short "previously on" and the most similar earlier scenes, so it knows the backstory and can pick clips that don't need it.
4. **Find candidates**: an LLM (Gemini) proposes promos around the peaks.
5. **Rules in code**: cuts snap to line boundaries, the clip starts on the hook (within 3 s), ends right after the cliffhanger, and stays 20–60 s.
6. **Judges**: a different LLM (gpt-oss on Groq) plays a stranger: would they stop scrolling in 3 seconds, can they follow it, is the ending open, what do they guess happens next, and is there ad-policy risk?
7. **Rank** with a weighted score and a variety step, then export.

Outputs: `promos_ranked.csv/json`, `promos_report.md`, one `.edl` edit list per promo, `rejected.csv` (with reasons) and `run_log.json` (models, tokens, cost).

## Run it

Needs Python 3.11+ (and Node 20 for the web app).

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # add GEMINI_API_KEY and GROQ_API_KEY (both have free tiers)
```

Find promos in a folder of `.txt` scripts:

```powershell
.venv\Scripts\python -m promo_finder --input "path\to\scripts" --out outputs\my_show
```

- `--offline` runs with no API keys (rule-based, lower quality).
- `--limit 5` reads only the first 5 episodes.
- `--generator` / `--judge` swap models, e.g. `--judge anthropic/claude-sonnet-5-5`.

Open the results in the web app:

```powershell
cd web; npm install; npm run build; cd ..
.venv\Scripts\python -m uvicorn server.app:app --port 7860
```

Then open http://localhost:7860. You can also upload a zip of scripts there and watch the run live.

## Change models

Every model is one line in `config.yaml` (any [LiteLLM](https://docs.litellm.ai) model id), with backup
models per role. If a free quota runs out, the tool switches to the next model. Every call is cached, so
re-runs are free.

## Check quality

```powershell
.venv\Scripts\python -m pytest tests                                   # rules and parser
.venv\Scripts\python eval\baseline.py --input <scripts> --out outputs\baseline
.venv\Scripts\python eval\evaluate.py --gold eval\gold_promos.csv --run outputs\my_show --run outputs\baseline
```

`eval/gold_promos.example.csv` shows the format for your own hand-picked promos.

## Known limits

- The AI tends to propose clips shorter than 20 s. Those that can't grow into their setup without breaking the 3-second hook are rejected (never stretched past the cliffhanger), so the pool to rank from is small.
- If the AI paraphrases a hook instead of quoting it, the 3-second rule can't be checked; these are flagged "hook line not found".
- The cold-viewer judge is lenient, and its probabilities are flat, so the ranking blends several signals instead of trusting one score.
- It reads text only: a purely visual hook is missed unless the script describes it.

## Project layout

```
promo_finder/   the pipeline (parse, signals, heartbeat, memory, llm, candidates, snap, judges, rank, export)
server/         FastAPI backend (job queue, live progress, access code, feedback, export)
web/            React web app
eval/           baseline and evaluation scripts
scripts/        deploy helpers (static Hugging Face Space, private demo dataset)
tests/          unit tests
```

The Kuku scripts and every output made from them are kept out of this repository.
