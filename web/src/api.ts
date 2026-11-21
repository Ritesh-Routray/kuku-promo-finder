export type Segment = { ep: number; start: number; end: number };
export type Judge = {
  cold_viewer: { who: string; what: string; want_next: string; understood: boolean; clarity: number };
  three_sec: { stop: boolean; score: number; why: string };
  cliffhanger: { unresolved: boolean; score: number };
  outcomes: { outcome: string; p: number }[];
  ad_risk: { level: "low" | "medium" | "high"; reason: string };
  suspense: number;
  surprise: number;
  what_really_happens: string;
  fallback?: boolean;
};
export type Promo = {
  id: string;
  rank: number;
  ep: number;
  title: string;
  segments: Segment[];
  duration: number;
  hook_line: string;
  hook_speaker: string;
  hook_at: number | null;
  cliffhanger_line: string;
  open_question: string;
  archetype: string;
  why: string;
  flags: string[];
  judge: Judge;
  scores: { score: number; parts: Record<string, number> };
  review_reasons: string[];
  feedback?: { verdict: string; note: string } | null;
};
export type Line = {
  ep: number; idx: number; scene: number; heading: string; kind: string; speaker: string;
  tags: string[]; start: number; end: number; text: string;
};
export type EpisodeSummary = { ep: number; logline: string; duration: number; n_lines: number; curve: number[]; peaks: number[] };
export type Episode = EpisodeSummary & { lines: Line[]; continuity: string };
export type RunSummary = {
  id: string; show: string; episodes: number; ranked: number; started: string; protected: boolean; status: string;
  models?: Record<string, string>; log?: any; events?: ProgressEvent[];
};
export type ProgressEvent = { stage: string; pct: number; msg: string; t?: string };

const codeKey = "pf_access_code";
export const getCode = () => { try { return sessionStorage.getItem(codeKey) || ""; } catch { return ""; } };
export const setCode = (c: string) => { try { sessionStorage.setItem(codeKey, c); } catch {} };

export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const code = getCode();
  if (code) headers.set("X-Access-Code", code);
  const r = await fetch(path, { ...init, headers });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

/** Static build (free hosting, no server): data comes from an encrypted file unlocked with the access code. */
export const STATIC = import.meta.env.VITE_STATIC === "1";

type Bundle = { run: RunSummary; promos: Promo[]; episodes: EpisodeSummary[]; details: Record<string, Episode> };
let bundle: Bundle | null = null;
let bundleCode = "";

async function decrypt(file: string, code: string): Promise<ArrayBuffer> {
  const buf = new Uint8Array(await (await fetch(file)).arrayBuffer());
  const salt = buf.slice(3, 19), iv = buf.slice(19, 31), body = buf.slice(31);
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(code), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: 600000, hash: "SHA-256" },
    base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
  let plain: ArrayBuffer;
  try { plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, body); }
  catch { throw new ApiError(403, "wrong access code"); }
  const stream = new Blob([plain]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).arrayBuffer();
}

async function unlocked(): Promise<Bundle> {
  const code = getCode();
  if (!code) throw new ApiError(403, "access code required");
  if (bundle && bundleCode === code) return bundle;
  bundle = JSON.parse(new TextDecoder().decode(await decrypt("data.enc", code)));
  bundleCode = code;
  return bundle!;
}

const fbKey = (pid: string) => `pf_fb_${pid}`;
const localFb = (pid: string) => { try { return JSON.parse(localStorage.getItem(fbKey(pid)) || "null"); } catch { return null; } };

const staticApi = {
  config: async () => ({ static: true, models: {}, suggested: { generator: [], judge: [] }, server_keys: {} }),
  runs: async (): Promise<RunSummary[]> => {
    if (bundle) return [bundle.run];
    return [await (await fetch("meta.json")).json()];
  },
  run: async (_id: string) => (await unlocked()).run,
  promos: async (_id: string) => (await unlocked()).promos.map((p) => ({ ...p, feedback: localFb(p.id) })),
  episodes: async (_id: string) => (await unlocked()).episodes,
  episode: async (_id: string, ep: number) => {
    const e = (await unlocked()).details[String(ep)];
    if (!e) throw new ApiError(404, "episode not found");
    return e;
  },
  feedback: async (_id: string, pid: string, verdict: string, note = "") => {
    const v = { verdict, note };
    try { localStorage.setItem(fbKey(pid), JSON.stringify(v)); } catch {}
    return v;
  },
  create: async (_f: FormData): Promise<{ id: string }> => { throw new ApiError(400, "Live analysis runs locally in this version."); },
  download: async (id: string) => {
    const zip = await decrypt("export.enc", getCode());
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([zip], { type: "application/zip" }));
    a.download = `promos_${id}.zip`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  },
};

const serverApi = {
  config: () => req<any>("/api/config"),
  runs: () => req<RunSummary[]>("/api/runs"),
  run: (id: string) => req<RunSummary>(`/api/runs/${id}`),
  promos: (id: string) => req<Promo[]>(`/api/runs/${id}/promos`),
  episodes: (id: string) => req<EpisodeSummary[]>(`/api/runs/${id}/episodes`),
  episode: (id: string, ep: number) => req<Episode>(`/api/runs/${id}/episodes/${ep}`),
  feedback: (id: string, pid: string, verdict: string, note = "") =>
    req(`/api/runs/${id}/promos/${pid}/feedback`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verdict, note }),
    }),
  create: (form: FormData) => req<{ id: string }>("/api/runs", { method: "POST", body: form }),
  download: async (id: string) => { location.href = `/api/runs/${id}/export?code=${encodeURIComponent(getCode())}`; },
};

export const api = STATIC ? staticApi : serverApi;

const myRunsKey = "pf_my_runs";
export const myRuns = (): { id: string; show: string }[] => {
  try { return JSON.parse(localStorage.getItem(myRunsKey) || "[]"); } catch { return []; }
};
export const rememberRun = (id: string, show: string) => {
  try {
    const list = myRuns().filter((r) => r.id !== id);
    localStorage.setItem(myRunsKey, JSON.stringify([{ id, show }, ...list].slice(0, 20)));
  } catch {}
};

export const fmt = (s: number) => {
  const m = Math.floor(Math.max(s, 0) / 60);
  const sec = Math.floor(Math.max(s, 0) % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};
export const fmtPrecise = (s: number) => {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${(s % 60).toFixed(2).padStart(5, "0")}`;
};

/** Strip quote marks the script already wraps dialogue in, so the UI can add its own. */
export const unq = (t: string) => t.trim().replace(/^["“”']+|["“”']+$/g, "");
