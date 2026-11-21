import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, unq, fmt, fmtPrecise, type Episode, type Line, type Promo } from "./api";
import { Icon, Poster, RiskPill, ScoreBar } from "./ui";

type Timed = { off: number; dur: number; line: Line };

function buildTimeline(promo: Promo, eps: Record<number, Episode>): Timed[] {
  const out: Timed[] = [];
  let offset = 0;
  for (const s of promo.segments) {
    const ep = eps[s.ep];
    if (ep) {
      for (const l of ep.lines) {
        if (l.start >= s.start - 0.05 && l.start < s.end) {
          out.push({ off: offset + l.start - s.start, dur: Math.min(l.end, s.end) - l.start, line: l });
        }
      }
    }
    offset += s.end - s.start;
  }
  return out;
}

export function Player({ runId, promos, promoId, go }: {
  runId: string; promos: Promo[]; promoId: string; go: (h: string) => void;
}) {
  const idx = promos.findIndex((p) => p.id === promoId);
  const promo = promos[idx];
  const [eps, setEps] = useState<Record<number, Episode>>({});
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [tab, setTab] = useState<"why" | "judges" | "segments">("why");
  const [fb, setFb] = useState(promo?.feedback?.verdict ?? "");
  const last = useRef<number>(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!promo) return;
    setT(0); setPlaying(false); setFb(promo.feedback?.verdict ?? "");
    const need = Array.from(new Set(promo.segments.map((s) => s.ep))).filter((e) => !eps[e]);
    Promise.all(need.map((e) => api.episode(runId, e))).then((list) =>
      setEps((old) => ({ ...old, ...Object.fromEntries(list.map((e) => [e.ep, e])) })));
  }, [promoId]);

  useEffect(() => {
    if (!playing || !promo) return;
    // setInterval (not requestAnimationFrame) so playback keeps time even in a background tab
    last.current = performance.now();
    const id = window.setInterval(() => {
      const now = performance.now();
      const dt = (now - last.current) / 1000;
      last.current = now;
      setT((v) => Math.min(v + dt, promo.duration));
    }, 100);
    return () => window.clearInterval(id);
  }, [playing, promo]);

  useEffect(() => { if (promo && playing && t >= promo.duration) setPlaying(false); }, [t, playing, promo]);

  const timeline = useMemo(() => (promo ? buildTimeline(promo, eps) : []), [promo, eps]);
  const nowIdx = timeline.reduce((acc, x, i) => (x.line.kind !== "camera" && x.off <= t + 0.01 ? i : acc), -1);

  useEffect(() => {
    const el = box.current?.querySelector(".pline.now") as HTMLElement | null;
    if (el && box.current) box.current.scrollTop = el.offsetTop - box.current.offsetTop - 80;
  }, [nowIdx]);

  if (!promo) return <div className="empty">Promo not found.</div>;
  const j = promo.judge;
  const pct = (v: number) => `${(v / promo.duration) * 100}%`;
  const segMarks: number[] = [];
  promo.segments.reduce((acc, s, i) => { if (i) segMarks.push(acc); return acc + s.end - s.start; }, 0);
  const prev = promos[idx - 1], next = promos[idx + 1];
  const hookLine = promo.hook_line.trim().slice(0, 40);

  const send = (v: string) => { setFb(v); api.feedback(runId, promo.id, v).catch(() => {}); };

  return (
    <>
      <div className="topbar">
        <button className="back" onClick={() => go(`#/`)} aria-label="Back"><Icon.back size={18} /></button>
        <h1>{promo.title}</h1>
        <span className="score-chip" style={{ fontSize: 13, padding: "6px 12px" }}>score {promo.scores.score}</span>
      </div>

      <div className="player">
        <div className="player-poster"><div className="deck glass">
          <Poster promo={promo} sub={`EPISODE ${String(promo.ep).padStart(2, "0")}`} />
          <h2>{promo.title}</h2>
          <div className="sub">{promo.archetype} · {fmt(promo.duration)} · {promo.segments.length} segment{promo.segments.length > 1 ? "s" : ""}</div>

          <div className="progress" onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            setT(((e.clientX - r.left) / r.width) * promo.duration);
          }}>
            <div className="progress-track" />
            <div className="progress-hook" style={{ left: 0, width: pct(3) }} title="first 3 seconds (hook zone)" />
            <div className="progress-fill" style={{ width: pct(t) }} />
            {segMarks.map((m) => <div key={m} className="progress-seg" style={{ left: pct(m) }} />)}
            <div className="progress-knob" style={{ left: pct(t) }} />
          </div>
          <div className="times"><span>{fmt(t)}</span><span>{fmt(promo.duration)}</span></div>
          <div className="controls">
            <button onClick={() => prev && go(`#/promo/${prev.id}`)} disabled={!prev} aria-label="Previous promo"><Icon.prev /></button>
            <button onClick={() => setT(Math.max(0, t - 5))} aria-label="Back 5 seconds"><Icon.rew /></button>
            <button className="play-big" onClick={() => { if (t >= promo.duration) setT(0); setPlaying(!playing); }} aria-label="Play">
              {playing ? <Icon.pause size={24} /> : <Icon.play size={24} />}
            </button>
            <button onClick={() => setT(Math.min(promo.duration, t + 5))} aria-label="Forward 5 seconds"><Icon.fwd /></button>
            <button onClick={() => next && go(`#/promo/${next.id}`)} disabled={!next} aria-label="Next promo"><Icon.next /></button>
          </div>
          <div className="next-up">{next ? `Next promo: ${next.title}` : "Last promo"}</div>
          <div className="verdict">
            <button className={`btn ${fb === "accept" ? "on-accept" : ""}`} onClick={() => send("accept")}><Icon.check size={16} /> Accept</button>
            <button className={`btn ${fb === "reject" ? "on-reject" : ""}`} onClick={() => send("reject")}><Icon.x size={16} /> Reject</button>
          </div>
        </div></div>

        <div className="grow">
          <div className="section-head" style={{ marginTop: 0 }}><h2>Timed script</h2><span>plays in real time · amber = first 3 seconds</span></div>
          <div className="prompter" ref={box}>
            {timeline.length === 0 && <div className="empty">Loading script…</div>}
            {timeline.map((x, i) => {
              const l = x.line;
              const isHook = hookLine && l.text.includes(hookLine.slice(0, 25));
              const cls = ["pline", l.kind === "camera" ? "camera" : "", i === nowIdx ? "now" : "", x.off + x.dur < t && i !== nowIdx ? "past" : ""].join(" ");
              return (
                <div key={i} className={cls} onClick={() => setT(x.off)} style={{ cursor: "pointer" }}>
                  <span className="t" style={x.off < 3 ? { color: "var(--amber)" } : undefined}>{fmt(x.off)}</span>
                  <span>
                    {l.kind === "dialogue" ? <span className="who">{l.speaker}</span> : l.kind !== "camera" ? <span className="who">{l.kind.toUpperCase()}</span> : null}
                    {l.tags.length > 0 && l.kind === "dialogue" && <span className="tags">({l.tags.join(", ")}) </span>}
                    {l.text}
                    {isHook && <span className="hook-mark">HOOK</span>}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="tabs">
            {(["why", "judges", "segments"] as const).map((k) => (
              <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
                {{ why: "Why it works", judges: "Judges", segments: "Segments & export" }[k]}
              </button>
            ))}
          </div>

          {tab === "why" && (
            <div className="card">
              <dl className="kv">
                <dt>Hook{promo.hook_at !== null ? ` · ${promo.hook_at}s` : ""}</dt><dd className="quote">“{unq(promo.hook_line)}”</dd>
                <dt>Cliffhanger</dt><dd className="quote">“{unq(promo.cliffhanger_line)}”</dd>
                <dt>Open question</dt><dd>{promo.open_question || "—"}</dd>
                <dt>Why it works</dt><dd>{promo.why}</dd>
              </dl>
              <div className="divider" />
              <div>
                <ScoreBar label="3-sec hook" v={promo.scores.parts.hook} />
                <ScoreBar label="Cliffhanger" v={promo.scores.parts.cliffhanger} />
                <ScoreBar label="Suspense" v={promo.scores.parts.suspense} />
                <ScoreBar label="Stands alone" v={promo.scores.parts.standalone} />
                <ScoreBar label="Heartbeat" v={promo.scores.parts.heartbeat} />
                <ScoreBar label="Early episode" v={promo.scores.parts.early_episode} />
              </div>
              {promo.review_reasons.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <div className="small muted" style={{ marginBottom: 6 }}>Needs a human look</div>
                  <div className="row wrap">{promo.review_reasons.map((r) => <span key={r} className="pill warn">{r}</span>)}</div>
                </div>
              )}
            </div>
          )}

          {tab === "judges" && (
            <div className="card">
              {j.fallback && <div className="error" style={{ marginBottom: 12 }}>LLM judge unavailable for this clip; heuristic scores shown.</div>}
              <div className="row wrap" style={{ marginBottom: 14 }}>
                <span className={`pill ${j.three_sec.stop ? "good" : "bad"}`}>3-sec test: {j.three_sec.stop ? "stops" : "scrolls"} ({j.three_sec.score}/10)</span>
                <span className={`pill ${j.cold_viewer.understood ? "good" : "warn"}`}>cold viewer: {j.cold_viewer.understood ? "understood" : "confused"} ({j.cold_viewer.clarity}/10)</span>
                <span className={`pill ${j.cliffhanger.unresolved ? "good" : "warn"}`}>cliffhanger {j.cliffhanger.score}/10</span>
                <RiskPill level={j.ad_risk.level} />
              </div>
              <dl className="kv">
                <dt>3-second verdict</dt><dd>{j.three_sec.why}</dd>
                <dt>Stranger sees</dt><dd>{j.cold_viewer.who}{j.cold_viewer.what ? `: ${j.cold_viewer.what}` : ""}</dd>
                <dt>Wants to know</dt><dd>{j.cold_viewer.want_next || "—"}</dd>
                <dt>Ad risk</dt><dd>{j.ad_risk.reason || "none flagged"}</dd>
              </dl>
              {j.outcomes.length > 0 && (
                <>
                  <div className="section-head"><h2>What happens next? (suspense {Math.round(j.suspense * 100)})</h2><span>guesses by the judge</span></div>
                  {j.outcomes.map((o, i) => (
                    <div key={i} className="outcome"><span>{o.outcome}</span><span className="p">{Math.round(o.p * 100)}%</span></div>
                  ))}
                  <div className="small muted" style={{ marginTop: 10 }}>
                    What really happens (surprise {Math.round(j.surprise * 100)}): {j.what_really_happens || "—"}
                  </div>
                </>
              )}
            </div>
          )}

          {tab === "segments" && (
            <div className="card">
              {promo.segments.map((s, i) => (
                <div key={i} className="outcome">
                  <span>Segment {i + 1} · Episode {s.ep} · <span className="mono">{fmtPrecise(s.start)} → {fmtPrecise(s.end)}</span></span>
                  <span className="p">{(s.end - s.start).toFixed(1)}s</span>
                </div>
              ))}
              {promo.flags.length > 0 && <div className="small muted" style={{ marginTop: 10 }}>Rule fixes: {promo.flags.join("; ")}</div>}
              <div className="row" style={{ marginTop: 16 }}>
                <button className="btn primary" onClick={() => api.download(runId)}><Icon.download size={16} /> Download all outputs (CSV, JSON, EDL)</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
