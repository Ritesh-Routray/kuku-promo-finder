import React, { useEffect, useMemo, useState } from "react";
import { api, unq, ApiError, STATIC, getCode, fmt, fmtPrecise, myRuns, rememberRun, setCode,
         type Episode, type EpisodeSummary, type ProgressEvent, type Promo, type RunSummary } from "./api";
import { Player } from "./Player";
import { Heartbeat, Icon, Poster, RiskPill, Sparkline, Spinner } from "./ui";

const useHash = () => {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => {
    const f = () => { setH(location.hash || "#/"); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return h;
};
const go = (h: string) => { location.hash = h; };
const runKey = "pf_current_run";

export default function App() {
  const hash = useHash();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string>(() => { try { return localStorage.getItem(runKey) || ""; } catch { return ""; } });
  const [promos, setPromos] = useState<Promo[] | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeSummary[] | null>(null);
  const [needCode, setNeedCode] = useState(false);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.runs().then((list) => {
      const mine = myRuns().map((r) => ({ id: r.id, show: r.show } as RunSummary));
      const all = [...list, ...mine.filter((m) => !list.some((l) => l.id === m.id))];
      setRuns(all);
      if (!runId && all.length) setRunId(all[0].id);
    }).catch((e) => setErr(String(e.message || e)));
  }, [reload]);

  useEffect(() => {
    if (!runId) return;
    try { localStorage.setItem(runKey, runId); } catch {}
    setPromos(null); setEpisodes(null); setErr("");
    Promise.all([api.promos(runId), api.episodes(runId)])
      .then(([p, e]) => {
        setPromos(p); setEpisodes(e); setNeedCode(false);
        if (STATIC) api.runs().then(setRuns);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setNeedCode(true);
        else setErr(String(e.message || e));
      });
  }, [runId, reload]);

  const route = hash.replace(/^#/, "").split("/").filter(Boolean);
  const page = route[0] || "";
  const run = runs.find((r) => r.id === runId);

  const nav = [
    { h: "#/", label: "Discover", icon: <Icon.home />, active: page === "" || page === "promo" },
    { h: "#/episodes", label: "Episodes", icon: <Icon.pulse />, active: page === "episodes" || page === "episode" },
    { h: "#/analyze", label: "Analyze", icon: <Icon.upload />, active: page === "analyze" || page === "progress" },
    { h: "#/about", label: "How it works", icon: <Icon.film />, active: page === "about" },
  ];

  let body: React.ReactNode;
  if (page === "analyze") body = STATIC ? <RunLocally /> : <Analyze />;
  else if (page === "progress") body = <Progress id={route[1]} onDone={(id) => { setRunId(id); setReload((x) => x + 1); go("#/"); }} />;
  else if (page === "about") body = <About />;
  else if (!runId) body = <div className="empty">No runs yet. <a className="btn primary" href="#/analyze">Analyze a show</a></div>;
  else if (err) body = <div className="error">{err}</div>;
  else if (needCode) body = <div className="empty"><span className="drop-ico"><Icon.lock size={20} /></span><p>This run contains confidential scripts. Enter the access code to view it.</p></div>;
  else if (!promos || !episodes) body = <Spinner />;
  else if (page === "promo") body = <Player runId={runId} promos={promos} promoId={route[1]} go={go} />;
  else if (page === "episodes") body = <Episodes episodes={episodes} promos={promos} />;
  else if (page === "episode") body = <EpisodeView runId={runId} ep={Number(route[1])} promos={promos} />;
  else body = <Discover run={run} promos={promos} episodes={episodes} />;

  return (
    <div className="shell">
      <div className="aura" aria-hidden><i /><i /><i /></div>
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><Icon.play size={15} /></span><span className="brand-name">Promo <em>Finder</em></span></div>
        <div className="nav-label">Workspace</div>
        {nav.map((n) => <a key={n.h} href={n.h} className={`nav-item ${n.active ? "active" : ""}`}>{n.icon}{n.label}</a>)}
        <div className="sidebar-foot">Finds 20–60s promos in microdrama screenplays: hook in 3s, cliffhanger ending, makes sense alone.</div>
      </aside>
      <main className="main">
        {(page === "" || page === "episodes") && runs.length > 0 && (
          <div className="row" style={{ justifyContent: "flex-end", marginBottom: -8 }}>
            <select className="run-select" value={runId} onChange={(e) => setRunId(e.target.value)} aria-label="Choose run">
              {runs.map((r) => <option key={r.id} value={r.id}>{r.protected ? "🔒 " : ""}{r.show || r.id}</option>)}
            </select>
          </div>
        )}
        {body}
      </main>
      <nav className="bottom-nav">
        {nav.map((n) => <a key={n.h} href={n.h} className={n.active ? "active" : ""}><span className="ico">{n.icon}</span>{n.label.split(" ")[0]}</a>)}
      </nav>
      {needCode && <CodeModal onSubmit={(c) => { setCode(c); setReload((x) => x + 1); }} />}
    </div>
  );
}

function CodeModal({ onSubmit }: { onSubmit: (c: string) => void }) {
  const [c, setC] = useState("");
  const tried = !!getCode();
  return (
    <div className="modal-bg">
      <form className="modal" onSubmit={(e) => { e.preventDefault(); onSubmit(c.trim()); }}>
        <span className="drop-ico" style={{ margin: 0 }}><Icon.lock size={20} /></span>
        <h3>Access code</h3>
        <p className="muted small">The demo show is confidential{STATIC ? " and stored encrypted" : ""}. The code is in the submission form.</p>
        {tried && <div className="error small" style={{ marginTop: 12 }}>That code didn't unlock the results. Check it and try again.</div>}
        <div className="field" style={{ margin: "14px 0" }}><input autoFocus value={c} onChange={(e) => setC(e.target.value)} placeholder="Enter code" /></div>
        <button className="btn primary block" type="submit">Unlock</button>
      </form>
    </div>
  );
}

function Discover({ run, promos, episodes }: { run?: RunSummary; promos: Promo[]; episodes: EpisodeSummary[] }) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const cats = useMemo(() => {
    const m = new Map<string, number>();
    promos.forEach((p) => m.set(p.archetype, (m.get(p.archetype) || 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
  }, [promos]);
  const list = promos.filter((p) => (!cat || p.archetype === cat) &&
    (!q || `${p.title} ${p.hook_line} ${p.cliffhanger_line} ${p.why}`.toLowerCase().includes(q.toLowerCase())));
  const top = list.slice(0, 8), rest = list.slice(8);
  const review = promos.filter((p) => p.review_reasons.length).length;
  const accepted = promos.filter((p) => p.feedback?.verdict === "accept").length;

  return (
    <>
      <header className="hero">
        <div>
          <div className="eyebrow">{run?.show || "Current show"}</div>
          <h1>The moments worth <em>posting</em> first.</h1>
          <p>Every clip opens on a hook inside three seconds and stops on an open question. Ranked, explained, and ready for an editor's yes or no.</p>
        </div>
      </header>
      <label className="search"><Icon.search size={18} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search hooks, lines, titles…" /></label>
      <div className="stats">
        <div className="stat"><b>{promos.length}</b><span>ranked promos</span></div>
        <div className="stat"><b>{episodes.length}</b><span>episodes read</span></div>
        <div className="stat"><b>{review}</b><span>need a human look</span></div>
        <div className="stat"><b>{accepted}</b><span>accepted by editor</span></div>
      </div>

      <div className="section-head"><h2>Story hooks</h2><span>{cat ? <a onClick={() => setCat("")} style={{ cursor: "pointer" }}>Clear filter</a> : "filter by archetype"}</span></div>
      <div className="chips">
        <button className={`chip ${!cat ? "active" : ""}`} onClick={() => setCat("")}>All <b>{promos.length}</b></button>
        {cats.map((c) => (
          <button key={c} className={`chip ${cat === c ? "active" : ""}`} onClick={() => setCat(cat === c ? "" : c)}>
            {c} <b>{promos.filter((p) => p.archetype === c).length}</b>
          </button>
        ))}
      </div>

      <div className="section-head"><h2>Post these first</h2><span>top {top.length} by score</span></div>
      <div className="grid">
        {top.map((p) => (
          <a key={p.id} className="tile" href={`#/promo/${p.id}`}>
            <Poster promo={p} sub={`EP ${p.ep}`} />
            <div className="tile-title" title={p.hook_line}>“{unq(p.hook_line)}”</div>
            <div className="tile-meta"><span className="mono">{fmt(p.duration)}</span>{p.review_reasons.length > 0 && <span style={{ color: "var(--warn)" }}>review</span>}<span className="score-chip">{p.scores.score}</span></div>
          </a>
        ))}
      </div>

      {rest.length > 0 && <div className="section-head"><h2>More promos</h2><span>{rest.length}</span></div>}
      <div className="list">
        {rest.map((p) => <PromoRow key={p.id} p={p} />)}
      </div>
      {list.length === 0 && <div className="empty">No promos match.</div>}
    </>
  );
}

function PromoRow({ p }: { p: Promo }) {
  return (
    <a className="list-row" href={`#/promo/${p.id}`}>
      <Poster promo={p} title={String(p.rank)} compact />
      <div className="grow">
        <div className="list-title">{p.title}</div>
        <div className="list-meta">
          <span>Episode {p.ep}</span><span className="mono">{fmt(p.duration)}</span><span style={{ textTransform: "capitalize" }}>{p.archetype}</span>
          {p.review_reasons.length > 0 && <span className="pill warn">review</span>}
          {p.judge.ad_risk.level !== "low" && <RiskPill level={p.judge.ad_risk.level} />}
        </div>
      </div>
      <div className="score">{p.scores.score}</div>
      <span className="play-sq"><Icon.play size={14} /></span>
    </a>
  );
}

function Episodes({ episodes, promos }: { episodes: EpisodeSummary[]; promos: Promo[] }) {
  return (
    <>
      <header className="hero"><div><div className="eyebrow">{episodes.length} episodes</div><h1>The show's <em>heartbeat</em>.</h1>
        <p>Each line traces drama intensity per second, built from emotion, events, sound cues and camera cutting.</p></div></header>
      <div className="list">
        {episodes.map((e) => {
          const n = promos.filter((p) => p.segments.some((s) => s.ep === e.ep)).length;
          return (
            <a key={e.ep} className="list-row" href={`#/episode/${e.ep}`}>
              <Poster title={String(e.ep)} compact />
              <div className="grow">
                <div className="list-title" style={{ fontSize: 14, fontWeight: 500 }}>{e.logline}</div>
                <div className="list-meta"><span>{fmt(e.duration)}</span><span>{e.n_lines} lines</span>{n > 0 && <span className="pill red">{n} promo{n > 1 ? "s" : ""}</span>}</div>
              </div>
              <Sparkline curve={e.curve} />
            </a>
          );
        })}
      </div>
    </>
  );
}

function EpisodeView({ runId, ep, promos }: { runId: string; ep: number; promos: Promo[] }) {
  const [e, setE] = useState<Episode | null>(null);
  const [cursor, setCursor] = useState<number | undefined>();
  useEffect(() => { api.episode(runId, ep).then(setE); }, [runId, ep]);
  if (!e) return <Spinner />;
  const mine = promos.filter((p) => p.segments.some((s) => s.ep === ep));
  const ranges = mine.flatMap((p) => p.segments.filter((s) => s.ep === ep));
  return (
    <>
      <div className="topbar">
        <button className="back" onClick={() => go("#/episodes")} aria-label="Back"><Icon.back size={18} /></button>
        <h1>Episode {ep}</h1>
        <span className="muted small">{fmt(e.duration)}</span>
      </div>
      <p className="muted">{e.logline}</p>
      <div className="card">
        <Heartbeat curve={e.curve} peaks={e.peaks} ranges={ranges} cursor={cursor} onSeek={setCursor} height={160} />
        <div className="hb-legend">
          <span><i style={{ background: "linear-gradient(90deg,#f0b45a,#ff7a68)" }} />drama intensity</span>
          <span><i style={{ background: "#0b0809", boxShadow: "0 0 0 1.5px #fff" }} />peaks sent to the LLM</span>
          <span><i style={{ background: "rgba(240,180,90,.5)" }} />chosen promo ranges</span>
          <span>click the chart to jump in the script</span>
        </div>
      </div>
      {mine.length > 0 && (<><div className="section-head"><h2>Promos from this episode</h2></div><div className="list">{mine.map((p) => <PromoRow key={p.id} p={p} />)}</div></>)}
      <div className="section-head"><h2>Script</h2><span>{e.lines.length} lines</span></div>
      <div className="prompter" style={{ maxHeight: 520 }}>
        {e.lines.filter((l) => l.kind !== "camera").map((l) => {
          const near = cursor !== undefined && l.start <= cursor + 1 && l.end >= cursor - 1;
          const inPromo = ranges.some((r) => l.start >= r.start && l.start < r.end);
          return (
            <div key={l.idx} className={`pline ${near ? "now" : ""}`} ref={(el) => { if (near && el) el.scrollIntoView({ block: "center", behavior: "smooth" }); }}
                 style={inPromo && !near ? { boxShadow: "inset 2px 0 0 rgba(240,180,90,.7)" } : undefined}>
              <span className="t">{fmtPrecise(l.start).slice(0, 5)}</span>
              <span>{l.kind === "dialogue" ? <span className="who">{l.speaker}</span> : <span className="who">{l.kind.toUpperCase()}</span>}{l.text}</span>
            </div>
          );
        })}
      </div>
    </>
  );
}

function Analyze() {
  const [files, setFiles] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [cfg, setCfg] = useState<any>(null);
  const [show, setShow] = useState("");
  const [gen, setGen] = useState("");
  const [judge, setJudge] = useState("");
  const [gk, setGk] = useState("");
  const [qk, setQk] = useState("");
  const [limit, setLimit] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.config().then((c) => { setCfg(c); setGen(c.models.generator); setJudge(c.models.judge); }); }, []);

  const submit = async () => {
    setBusy(true); setErr("");
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    f.append("show", show); f.append("generator", gen); f.append("judge", judge);
    f.append("gemini_key", gk); f.append("groq_key", qk); f.append("limit", String(limit || 0));
    try {
      const { id } = await api.create(f);
      rememberRun(id, show || "Uploaded show");
      go(`#/progress/${id}`);
    } catch (e: any) { setErr(e.message); setBusy(false); }
  };

  return (
    <>
      <header className="hero"><div><div className="eyebrow">New run</div><h1>Analyze a <em>new show</em>.</h1>
        <p>Drop the episode scripts and pick the models. Progress streams live; results open on the board when the run finishes.</p></div></header>
      <div className="card">
        <label className={`drop ${over ? "over" : ""}`}
               onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
               onDrop={(e) => { e.preventDefault(); setOver(false); setFiles([...e.dataTransfer.files]); }}>
          <input type="file" multiple accept=".zip,.txt" style={{ display: "none" }} onChange={(e) => setFiles([...(e.target.files || [])])} />
          <span className="drop-ico"><Icon.upload size={22} /></span>
          <div style={{ fontWeight: 600, color: "var(--text)" }}>{files.length ? `${files.length} file(s) selected` : "Drop a .zip of episode scripts, or click to choose"}</div>
          <div className="small" style={{ marginTop: 6 }}>Same screenplay format as the Kuku pack: timestamped scenes, lines and actions. Uploaded scripts are deleted after the run.</div>
        </label>
        <div className="form-grid" style={{ marginTop: 18 }}>
          <label className="field">Show name<input value={show} onChange={(e) => setShow(e.target.value)} placeholder="e.g. Secret Billionaire" /></label>
          <label className="field">Episodes to read (0 = all)<input type="number" min={0} value={limit} onChange={(e) => setLimit(Number(e.target.value))} /></label>
          <label className="field">Generator model
            <input list="gens" value={gen} onChange={(e) => setGen(e.target.value)} />
            <datalist id="gens">{cfg?.suggested.generator.map((m: string) => <option key={m} value={m} />)}</datalist>
          </label>
          <label className="field">Judge model
            <input list="judges" value={judge} onChange={(e) => setJudge(e.target.value)} />
            <datalist id="judges">{cfg?.suggested.judge.map((m: string) => <option key={m} value={m} />)}</datalist>
          </label>
          <label className="field">Gemini API key {cfg?.server_keys.gemini ? "(optional, server has one)" : ""}<input type="password" value={gk} onChange={(e) => setGk(e.target.value)} placeholder="only sent with this run, never stored" /></label>
          <label className="field">Groq API key {cfg?.server_keys.groq ? "(optional, server has one)" : ""}<input type="password" value={qk} onChange={(e) => setQk(e.target.value)} placeholder="only sent with this run, never stored" /></label>
        </div>
        <p className="small muted">Any LiteLLM model id works (gemini/…, groq/…, openai/…, anthropic/…). Use <b>heuristic</b> for a no-key, rule-based run.</p>
        {err && <div className="error" style={{ marginBottom: 12 }}>{err}</div>}
        <button className="btn primary block" disabled={!files.length || busy} onClick={submit}>{busy ? "Uploading…" : "Find promos"}</button>
      </div>
    </>
  );
}

const STAGES = [["parse", "Read screenplays"], ["signals", "Score emotion (local model)"], ["heartbeat", "Build drama heartbeat"],
  ["memory", "Index story memory"], ["candidates", "Find promo moments (LLM)"], ["rules", "Snap cuts + check rules"],
  ["judges", "Cold-viewer, 3-second & suspense judges"], ["rank", "Rank with variety"], ["export", "Write outputs"]];

function Progress({ id, onDone }: { id: string; onDone: (id: string) => void }) {
  const [ev, setEv] = useState<ProgressEvent[]>([]);
  const [status, setStatus] = useState("queued");
  useEffect(() => {
    const es = new EventSource(`/api/runs/${id}/events`);
    es.addEventListener("progress", (m) => setEv((x) => [...x, JSON.parse((m as MessageEvent).data)]));
    es.addEventListener("end", (m) => { setStatus(JSON.parse((m as MessageEvent).data).status); es.close(); });
    es.onerror = () => { es.close(); api.run(id).then((r) => setStatus(r.status)).catch(() => setStatus("error")); };
    return () => es.close();
  }, [id]);
  const last = ev[ev.length - 1];
  const cur = last?.stage;
  const curIdx = STAGES.findIndex(([s]) => s === cur);
  return (
    <>
      <div className="topbar"><h1>Finding promos…</h1><span className="pill red">{status}</span></div>
      <div className="card">
        <div className="progress" style={{ cursor: "default" }}>
          <div className="progress-track" /><div className="progress-fill" style={{ width: `${last?.pct ?? 0}%` }} />
          <div className="progress-knob" style={{ left: `${last?.pct ?? 0}%` }} />
        </div>
        <div className="times"><span>{last?.msg ?? "Waiting in queue"}</span><span>{Math.round(last?.pct ?? 0)}%</span></div>
        <div className="stages">
          {STAGES.map(([s, label], i) => (
            <div key={s} className={`stage ${status === "done" || i < curIdx ? "done" : i === curIdx ? "now" : ""}`}><span className="dot" />{label}</div>
          ))}
        </div>
        <div className="log">{ev.map((e, i) => <div key={i}>[{e.stage}] {e.msg}</div>)}</div>
        {status === "done" && <button className="btn primary block" style={{ marginTop: 16 }} onClick={() => onDone(id)}>Open results</button>}
        {status === "error" && <div className="error" style={{ marginTop: 16 }}>The run failed: {last?.msg}</div>}
      </div>
    </>
  );
}

function About() {
  const steps = [
    ["Parse", "Code reads every scene, line, action and camera shot with its exact timestamps."],
    ["Drama heartbeat", "A local emotion model plus the script's own emotion tags, event words, sound cues and camera cutting give an intensity curve per second."],
    ["Story memory (RAG)", "Earlier episodes' summaries and the most similar earlier scenes are retrieved so the LLM knows the story without the viewer needing to."],
    ["Candidates", "The generator LLM proposes promos per episode, guided by the heartbeat peaks."],
    ["Rules", "Code snaps cuts to line and shot boundaries, moves the start onto the hook (≤3s), cuts right after the cliffhanger and enforces 20–60s."],
    ["Judges", "A different LLM family plays a stranger: does the first 3 seconds stop the scroll, can they follow it cold, is the ending open, what do they guess happens next (suspense), and would ad review flag it?"],
    ["Rank", "Weighted score with variety (MMR) so the top list is not five cuts of the same scene. Disagreements are routed to a human."],
  ];
  return (
    <>
      <header className="hero"><div><div className="eyebrow">Method</div><h1>From screenplay to <em>shortlist</em>.</h1>
        <p>Code does what must be exact, small local models read the emotion, and two different LLM families propose and judge. A person makes the final call.</p></div></header>
      <div className="list">
        {steps.map(([t, d], i) => (
          <div key={t} className="list-row" style={{ alignItems: "flex-start" }}>
            <span className="step-num">{i + 1}</span>
            <div className="grow"><div className="list-title">{t}</div><div className="muted small" style={{ marginTop: 4, lineHeight: 1.5 }}>{d}</div></div>
          </div>
        ))}
      </div>
    </>
  );
}

function RunLocally() {
  const cmds = [
    ["Install", "python -m venv .venv\n.venv\\Scripts\\pip install -r requirements.txt"],
    ["Add keys", "copy .env.example .env   # then add GEMINI_API_KEY and GROQ_API_KEY"],
    ["Find promos", "python -m promo_finder --input <folder of .txt scripts> --out outputs/my_show"],
    ["Open this app on it", "uvicorn server.app:app --port 7860   # then open http://localhost:7860"],
  ];
  return (
    <>
      <header className="hero"><div><div className="eyebrow">New run</div><h1>Analyze a <em>new show</em>.</h1>
        <p>This hosted copy is read-only so it can run free with no server. Live analysis of a new show runs from the code repository in four steps; add <span className="mono">--offline</span> to run with no API keys.</p></div></header>
      <div className="list">
        {cmds.map(([t, c], i) => (
          <div key={t} className="list-row" style={{ alignItems: "flex-start" }}>
            <span className="step-num">{i + 1}</span>
            <div className="grow"><div className="list-title">{t}</div>
              <pre className="mono" style={{ margin: "8px 0 0", whiteSpace: "pre-wrap", color: "var(--muted)" }}>{c}</pre></div>
          </div>
        ))}
      </div>
    </>
  );
}
