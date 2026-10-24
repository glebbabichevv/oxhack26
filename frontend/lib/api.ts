// Types and fetchers for the Horizon API (CLAUDE.md → API contract v1.1).

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Action = "BUY_YES" | "BUY_NO" | "NO_TRADE";

export type LiveMarket = {
  market_id: string;
  question: string;
  domain: string;
  price_yes: number;
  hours_to_resolution: number;
  q_yes: number;
  q_low: number;
  q_high: number;
  edge: number;
  net_edge: number;
  cost: number;
  action: Action;
  kelly_fraction: number;
  reason: string;
  url: string;
  volume_usd: number;
  fee?: number;
  wait?: boolean; // edge now, but policy V3 enters only within 24 h of the end
  would_be?: Action | null;
  check_back_in_hours?: number | null;
};

// /api/live (contract v1.3): computed from live Polymarket prices on request; "fallback" = saved snapshot.
export type LivePayload = {
  updated_at: string | null;
  model_version: string | null;
  source: "live" | "fallback";
  error?: string;
  markets: LiveMarket[];
};

export type CalibrationBin = { price_mid: number; observed: number; model: number; n: number };
export type CalibrationHorizon = {
  horizon_hours: number;
  n: number;
  bins: CalibrationBin[];
  brier_market: number;
  brier_model: number;
  logloss_market: number;
  logloss_model: number;
};
export type Calibration = { horizons: CalibrationHorizon[] };

export type EquityPoint = { t: string; value: number };
export type Run = { n_trades: number; return: number; hit_rate: number; max_drawdown: number; avg_edge?: number; equity: EquityPoint[] };
export type HorizonRun = { n_trades: number; mean_return_per_trade: number | null; hit_rate: number | null };
export type PolicyStats = { per_dollar: number; per_dollar_ci: [number, number]; return: number; return_ci: [number, number]; n_trades: number; max_drawdown: number };
export type Failure = { kind: "losing_domain" | "no_lift" | "thin_data"; domain?: string; horizon_hours?: number; n?: number; text: string };
export type WorstTrade = { question: string; action: Action; price_yes: number; q_yes: number; outcome: number; horizon_hours: number; ret: number };

export type Backtest = {
  cutoff: string;
  n_train_markets: number;
  n_test_markets: number;
  n_trades: number;
  model_selection?: { chosen: string; val_markets: number; val_logloss: Record<string, number> };
  with_costs: Run;
  without_costs: Run;
  naive_favourite: { return: number; n_trades?: number; hit_rate?: number };
  overall: { brier_market: number; brier_model: number; logloss_market: number; logloss_model: number };
  by_horizon: { horizon_hours: number; n_markets: number; with_costs: HorizonRun; without_costs: HorizonRun }[];
  failures: Failure[];
  worst_trades: WorstTrade[];
  assumptions: string[];
  return_ci?: [number, number];
  generated_at?: string;
  model_version?: string;
  peak_open_stake?: number;
  return_per_dollar_staked?: number;
  return_per_dollar_ci?: [number, number];
  headline?: PolicyStats & { policy: string; hit_rate: number; peak_open_stake: number; note: string };
  policy?: { name: string; min_edge: number; enter_from_hours: number; note: string };
  robustness?: { both?: PolicyStats; price_le_1h?: PolicyStats; closed_ge_12h?: PolicyStats };
  policy_comparison?: { note: string; rows: { variant: string; label: string; picked_by_validation: boolean; validation: PolicyStats; test: PolicyStats }[]; round2?: { variant: string; picked_by_validation: boolean; validation: PolicyStats; test: PolicyStats }[] } | null;
  capped_exposure?: Run & { return_ci?: [number, number]; cap: number; return_per_dollar_staked?: number };
  by_domain?: { domain: string; n_trades: number; return: number; hit_rate: number; return_ci?: [number, number] }[];
};

// ---- offline fallback (venue Wi-Fi): every good response is kept in localStorage; on failure the
// last copy is returned and its time is recorded, so the page can say "cached at HH:MM". ----

const CACHE = "hz-cache:";
const cachedPaths = new Map<string, number>();
const listeners = new Set<() => void>();

function readCache<T>(path: string): { t: number; data: T } | undefined {
  try { const raw = localStorage.getItem(CACHE + path); return raw ? JSON.parse(raw) : undefined; } catch { return undefined; }
}

export async function getJSON<T>(path: string): Promise<T> {
  try {
    const res = await fetch(`${API_URL}${path}`);
    if (!res.ok) throw new Error(`${path}: ${res.status}`);
    const data = (await res.json()) as T;
    try { localStorage.setItem(CACHE + path, JSON.stringify({ t: Date.now(), data })); } catch { /* storage full or blocked */ }
    if (cachedPaths.delete(path)) listeners.forEach((f) => f());
    return data;
  } catch (e) {
    const hit = readCache<T>(path);
    if (!hit) throw e;
    cachedPaths.set(path, hit.t);
    listeners.forEach((f) => f());
    return hit.data;
  }
}

/** Earliest cache time among paths served from the offline copy (prefix match), or undefined if all live. */
export function cachedAt(prefixes: string[]): number | undefined {
  let t: number | undefined;
  cachedPaths.forEach((v, k) => { if (prefixes.some((p) => k.startsWith(p)) && (t === undefined || v < t)) t = v; });
  return t;
}
export function onCacheChange(f: () => void) { listeners.add(f); return () => { listeners.delete(f); }; }
export const hhmm = (t: number) => new Date(t).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

// ---- formatting (DESIGN.md → The Tabular Rule: every number carries its unit) ----

export const cents = (p: number) => `${Math.round(p * 100)}¢`;
export const pct = (p: number, digits = 0) => `${(p * 100).toFixed(digits)}%`;
// Backtest P&L is additive, in units of the starting bankroll: 2.77 → "+277%" (of starting bankroll), not a multiple.
export const bankroll = (x: number) => `${x >= 0 ? "+" : "−"}${Math.round(Math.abs(x) * 100).toLocaleString("en-GB")}%`;
export const int = (n: number) => n.toLocaleString("en-GB");

export function horizonShort(h: number) {
  if (h >= 24) return `${Math.round(h / 24)}d`;
  return `${Math.round(h)}h`;
}

export function horizonPhrase(h: number) {
  const words: Record<number, string> = { 720: "A month out", 168: "A week out", 72: "Three days out", 24: "A day out", 12: "Twelve hours out" };
  return words[h] ?? `${horizonShort(h)} out`;
}

export function horizonLabel(h: number) {
  const words: Record<number, string> = { 720: "1 month out", 168: "1 week out", 72: "3 days out", 24: "1 day out", 12: "12 hours out" };
  return words[h] ?? `${horizonShort(h)} out`;
}

export function dateLong(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}
