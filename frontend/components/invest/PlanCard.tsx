"use client";

import { useState } from "react";
import { Button } from "@/design/components/Button";
import { PAUSE, money, postWithPin, type PlanSummary } from "@/lib/invest";

function ago(iso: string | null) {
  if (!iso) return "not yet";
  const min = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  return min < 1 ? "just now" : min < 60 ? `${min} min ago` : `${Math.round(min / 60)} h ago`;
}

export function PlanCard({ plan, intervalMin, pin, onChange }: { plan: PlanSummary; intervalMin: number; pin: string; onChange: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(action: "pause" | "resume" | "stop") {
    if (action === "stop" && !window.confirm("Stop this plan? It will not place new bets. Open bets still settle.")) return;
    setBusy(true);
    setError(null);
    try {
      await postWithPin(`/api/plans/${plan.id}/${action}`, pin);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const status =
    plan.status === "running" ? `Running · checks every ${intervalMin} min · last check ${ago(plan.last_check)}`
    : plan.status === "paused" ? `Paused: ${PAUSE[plan.pause_reason ?? ""] ?? plan.pause_reason}`
    : "Stopped · open bets will settle on their own";

  return (
    <div className="rounded-2xl border border-hairline p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[17px] font-semibold text-ink-strong">{money(plan.budget)} plan</span>
        <span className={`text-[15px] font-semibold tabular-nums ${plan.profit >= 0 ? "text-up" : "text-down"}`}>
          {plan.profit >= 0 ? "Up" : "Down"} {money(plan.profit, true)} ({(plan.profit_pct * 100).toFixed(1)}%)
        </span>
      </div>
      <p className="mt-1 text-[14px] text-ink-muted" aria-live="polite">{status}</p>
      <p className="mt-1 text-[14px] text-ink-muted tabular-nums">{plan.open_bets} open bets · {money(plan.cash)} cash not yet used · max {money(plan.max_bet)} per bet</p>
      {plan.status !== "stopped" ? (
        <div className="mt-4 flex flex-wrap gap-3">
          {plan.status === "running"
            ? <Button className="h-11 px-6" onClick={() => act("pause")} disabled={busy || !pin}>Pause</Button>
            : <Button className="h-11 px-6" onClick={() => act("resume")} disabled={busy || !pin}>Resume</Button>}
          <Button variant="quiet" className="h-11 px-6" onClick={() => act("stop")} disabled={busy || !pin}>Stop</Button>
        </div>
      ) : null}
      {error ? <p role="alert" className="mt-3 text-[14px] font-medium text-down">{error}</p> : null}
    </div>
  );
}
