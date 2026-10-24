// Types, fetchers and plain-English copy for the invest dashboard (/api/plans, /api/orders, /api/pnl).
import { API_URL, cents, pct } from "@/lib/api";

// The trader runs on an always-on host; on a single-server setup it is the same as the main API.
export const TRADER_URL = (process.env.NEXT_PUBLIC_TRADER_URL ?? API_URL).replace(/\/$/, "");

export type PlanStatus = "running" | "paused" | "stopped";
export type PlanSummary = {
  id: string; status: PlanStatus; pause_reason: string | null; budget: number; max_bet: number;
  daily_loss_stop: number; cash: number; value: number; profit: number; profit_pct: number;
  open_bets: number; last_check: string | null; created_at: string;
};
export type PlansPayload = { mode: "paper" | "live"; interval_min: number; max_bet_ceiling: number; plans: PlanSummary[] };
export type InvestEvent = {
  id: string; plan_id: string | null; kind: "start" | "buy" | "skip" | "settle" | "pause" | "resume" | "stop" | "error";
  t: string; question?: string; side?: "YES" | "NO"; cost?: number; price?: number; p_model?: number;
  hours_to_resolution?: number; outcome?: 0 | 1; payout?: number; pnl?: number; reason?: string; text?: string;
  url?: string; budget?: number;
  possible_fill?: boolean; prev_reason?: string | null;
};
export type Pnl = { real: { t: string; value: number }[]; backtest: { t: string; value: number }[]; backtest_budget: number };

export async function getTrader<T>(path: string): Promise<T> {
  const res = await fetch(`${TRADER_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function postWithPin<T>(path: string, pin: string, body?: unknown): Promise<T> {
  const res = await fetch(`${TRADER_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Dashboard-Pin": pin },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Request failed (${res.status})`);
  return data as T;
}

export const money = (x: number, signed = false) => {
  const s = `$${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 2 })}`;
  return signed ? `${x >= 0 ? "+" : "−"}${s}` : `${x < 0 ? "−" : ""}${s}`;
};

const when = (h?: number) => (h === undefined ? "" : h < 24 ? `in ${Math.max(1, Math.round(h))} hours` : `in ${Math.round(h / 24)} days`);

const SKIP: Record<string, string> = {
  edge_vanished: "the price moved and the edge was gone",
  below_minimum: "the bet was below Polymarket's minimum size",
  no_liquidity: "nobody was selling at a fair price",
};
export const PAUSE: Record<string, string> = {
  daily_loss: "today's loss passed the limit you set",
  polymarket_errors: "Polymarket returned errors three times in a row",
  stale_data: "the model's prices were more than 2 hours old",
  by_person: "someone pressed Pause",
  check_fill: "an order may have gone through without being recorded. Check Polymarket before resuming",
};

export function sentence(e: InvestEvent): { text: string; tone: "up" | "down" | "muted"; chip: string } {
  const q = e.question ? `“${e.question}”` : "";
  switch (e.kind) {
    case "buy":
      return { chip: "Open", tone: "muted",
        text: `Bought ${e.side} on ${q} at ${cents(e.price ?? 0)}, ${money(e.cost ?? 0)}. Model thinks ${pct(e.p_model ?? 0)}. Settles ${when(e.hours_to_resolution)}.` };
    case "settle":
      return e.outcome
        ? { chip: `Won ${money(e.pnl ?? 0, true)}`, tone: "up", text: `${e.side} on ${q} won. Paid out ${money(e.payout ?? 0)}.` }
        : { chip: `Lost ${money(e.pnl ?? 0, true)}`, tone: "down", text: `${e.side} on ${q} lost.` };
    case "skip": {
      const why = SKIP[e.reason ?? ""] ?? e.reason;
      return { chip: "Skipped", tone: "muted", text: why ? `Skipped ${q}: ${why}.` : `Skipped ${q}.` };
    }
    case "pause": {
      const why = PAUSE[e.reason ?? ""] ?? e.reason;
      return { chip: "Paused", tone: "down", text: why ? `Investing paused because ${why}.` : "Investing paused." };
    }
    case "start":
      return { chip: "Started", tone: "muted", text: `New plan started with ${money(e.budget ?? 0)}.` };
    case "resume":
      return { chip: "Resumed", tone: "muted", text: "Investing resumed." };
    case "stop":
      return { chip: "Stopped", tone: "muted", text: "Plan stopped. Open bets will settle on their own." };
    default:
      if (e.possible_fill) {
        return { chip: "Check", tone: "down", text: `An order on ${q} may have gone through but wasn't recorded. Check Polymarket.` };
      }
      return { chip: "Problem", tone: "down", text: `Something went wrong talking to Polymarket${e.text ? `: ${e.text}` : ""}.` };
  }
}
