import React from "react";
import type { Promo } from "./api";

const P = (d: string) => (props: { size?: number }) => (
  <svg width={props.size ?? 20} height={props.size ?? 20} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
);
export const Icon = {
  home: P("M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z"),
  film: P("M4 4h16v16H4zM4 9h16M4 15h16M9 4v16M15 4v16"),
  pulse: P("M3 12h4l3-8 4 16 3-8h4"),
  upload: P("M12 16V4m0 0-5 5m5-5 5 5M4 20h16"),
  back: P("m15 18-6-6 6-6"),
  search: P("m21 21-4.3-4.3M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15z"),
  play: (p: { size?: number }) => (
    <svg width={p.size ?? 20} height={p.size ?? 20} viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M8 5.5v13l11-6.5z" /></svg>
  ),
  pause: (p: { size?: number }) => (
    <svg width={p.size ?? 20} height={p.size ?? 20} viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>
  ),
  prev: P("M19 20 9 12l10-8zM5 19V5"),
  next: P("m5 4 10 8-10 8zM19 5v14"),
  rew: P("M11 19 2 12l9-7zM22 19l-9-7 9-7z"),
  fwd: P("m13 19 9-7-9-7zM2 19l9-7-9-7z"),
  download: P("M12 4v12m0 0 5-5m-5 5-5-5M4 20h16"),
  check: P("M20 6 9 17l-5-5"),
  x: P("M18 6 6 18M6 6l12 12"),
  lock: P("M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4"),
};

// Muted, film-like duotones: each poster gets a deep base and a soft light leak.
const PALETTES: [string, string, string][] = [
  ["#3a0d10", "#b5382c", "#e8935a"], ["#1d1030", "#5b3a9a", "#d07a8c"], ["#0b2229", "#2d6b74", "#c9b48a"],
  ["#2a1608", "#9a5a1c", "#f0c27a"], ["#2b0b20", "#8a2c5c", "#f09a8a"], ["#121a12", "#3f5e3a", "#d8c48a"],
  ["#17161c", "#4a4658", "#c7b8a8"], ["#300f0a", "#a33a22", "#f2b06a"],
];
export function hash(s: string) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0;
  return Math.abs(h);
}
export function palette(key: string) {
  const h = hash(key);
  const [base, mid, leak] = PALETTES[h % PALETTES.length];
  const x = 20 + (h % 60), y = 10 + ((h >> 3) % 30);
  return `radial-gradient(70% 55% at ${x}% ${y}%, ${leak}cc 0%, transparent 60%), ` +
         `radial-gradient(120% 90% at ${100 - x}% 100%, ${mid} 0%, transparent 70%), ${base}`;
}

export function Poster({ promo, title, sub, showRank = true, compact = false }: {
  promo?: Promo; title?: string; sub?: string; showRank?: boolean; compact?: boolean;
}) {
  const t = title ?? promo?.title ?? "";
  const key = promo ? promo.archetype + promo.id : t;
  if (compact) return <div className="poster" style={{ background: palette(key) }}><div className="poster-title">{t}</div></div>;
  return (
    <div className="poster" style={{ background: palette(key) }}>
      {promo && showRank && <span className="poster-num">{String(promo.rank).padStart(2, "0")}</span>}
      {sub && <span className="poster-ep">{sub}</span>}
      <div className="poster-rule" />
      <div className="poster-title">{t}</div>
      {promo && <div className="poster-kind">{promo.archetype}</div>}
    </div>
  );
}

export function ScoreBar({ label, v }: { label: string; v: number }) {
  return (
    <div className="score-row">
      <span className="muted">{label}</span>
      <div className="bar"><i style={{ width: `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%` }} /></div>
      <span>{Math.round(v * 100)}</span>
    </div>
  );
}

export function RiskPill({ level }: { level: string }) {
  const cls = level === "high" ? "bad" : level === "medium" ? "warn" : "good";
  return <span className={`pill ${cls}`}>ad risk: {level}</span>;
}

/** Area chart of the drama heartbeat with peaks and promo ranges. */
export function Heartbeat({ curve, peaks = [], ranges = [], height = 140, cursor, onSeek }: {
  curve: number[]; peaks?: number[]; ranges?: { start: number; end: number; label?: string }[];
  height?: number; cursor?: number; onSeek?: (t: number) => void;
}) {
  const w = 1000;
  const n = Math.max(curve.length - 1, 1);
  const x = (t: number) => (t / n) * w;
  const y = (v: number) => height - 6 - v * (height - 16);
  const path = curve.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <div className="hb">
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" style={{ height, cursor: onSeek ? "pointer" : undefined }}
           onClick={(e) => {
             if (!onSeek) return;
             const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
             onSeek(((e.clientX - r.left) / r.width) * n);
           }}>
        <defs>
          <linearGradient id="hbfill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#f2554a" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#f2554a" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="hbline" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#f0b45a" /><stop offset="100%" stopColor="#ff7a68" />
          </linearGradient>
        </defs>
        {ranges.map((r, i) => (
          <rect key={i} x={x(r.start)} y={0} width={Math.max(x(r.end) - x(r.start), 2)} height={height} fill="#f0b45a" opacity={0.13} />
        ))}
        <path d={`${path} L${w},${height} L0,${height} Z`} fill="url(#hbfill)" />
        <path d={path} fill="none" stroke="url(#hbline)" strokeWidth={1.75} vectorEffect="non-scaling-stroke" />
        {peaks.map((p) => (
          <circle key={p} cx={x(p)} cy={y(curve[p] ?? 0)} r={3.5} fill="#0b0809" stroke="#fff" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        ))}
        {cursor !== undefined && <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={height} stroke="rgba(255,255,255,.7)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  );
}

export function Sparkline({ curve }: { curve: number[] }) {
  const w = 120, h = 28, n = Math.max(curve.length - 1, 1);
  const d = curve.map((v, i) => `${i ? "L" : "M"}${((i / n) * w).toFixed(1)},${(h - 2 - v * (h - 4)).toFixed(1)}`).join(" ");
  return <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden><path d={d} fill="none" stroke="#ff8f82" strokeOpacity={0.8} strokeWidth={1.25} /></svg>;
}

export function Spinner() {
  return <div className="spinner" role="status" aria-label="Loading"><i /></div>;
}
