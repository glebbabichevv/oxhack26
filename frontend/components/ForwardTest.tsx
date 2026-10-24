"use client";

import { useEffect, useState } from "react";
import { bankroll, getJSON, int } from "@/lib/api";

// Forward test: live calls frozen (and committed) before their outcomes, scored as markets resolve.
// Renders nothing until GET /api/forward exists, and says "resolving…" until there are enough resolved trades.

export type Forward = {
  frozen_at: string;
  commit_url?: string;
  n_markets: number;
  n_trades: number;
  n_resolved: number;
  n_trades_resolved: number;
  n_won: number;
  pnl: number; // starting-bankroll units, with costs
  updated_at?: string;
};

const MIN_RESOLVED = 5;

const london = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });

export function ForwardTest({ data }: { data?: Forward } = {}) {
  const [fetched, setF] = useState<Forward | null>();
  useEffect(() => {
    if (data) return;
    getJSON<Forward>("/api/forward").then(setF).catch(() => setF(null));
  }, [data]);
  const f = data ?? fetched;
  if (!f) return null;

  const enough = f.n_trades_resolved >= MIN_RESOLVED;
  return (
    <div className="mt-5 border-t border-hairline-soft pt-3 text-[13px]">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="font-semibold text-ink-strong">Forward test</span>
        <span className="text-[12px] text-ink-faint">
          calls frozen {london(f.frozen_at)}, before the outcomes
          {f.commit_url ? <> · <a href={f.commit_url} target="_blank" rel="noreferrer" className="underline decoration-hairline underline-offset-4 hover:text-ink-muted">see the commit</a></> : null}
        </span>
      </div>
      <div className="mt-1.5 tabular-nums text-ink-muted">
        {int(f.n_markets)} markets · {int(f.n_trades)} trades · {int(f.n_resolved)} resolved so far
        {enough ? (
          <>
            {" · "}
            {int(f.n_won)} of {int(f.n_trades_resolved)} trades won · P&amp;L{" "}
            <b className={`font-semibold ${f.pnl >= 0 ? "text-up" : "text-down"}`}>{bankroll(f.pnl)}</b> of bankroll
          </>
        ) : (
          <> · <span className="text-ink-strong">resolving…</span></>
        )}
      </div>
      <p className="mt-1 text-[12px] text-ink-faint">
        {!enough
          ? `Scored once ${MIN_RESOLVED}+ traded markets resolve. Until then the backtest is the evidence.`
          : f.n_trades_resolved < 100
            ? "Too few trades to judge; the backtest is the evidence."
            : "Resolved trades only, with costs."}
      </p>
    </div>
  );
}
