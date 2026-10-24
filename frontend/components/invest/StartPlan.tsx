"use client";

import { useState } from "react";
import { Button } from "@/design/components/Button";
import { money, postWithPin, type PlanSummary } from "@/lib/invest";

const field = "mt-1.5 h-12 w-full rounded-xl border border-hairline bg-white px-4 text-[18px] tabular-nums text-ink-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-strong";

export function StartPlan({ ceiling, pin, onDone }: { ceiling: number; pin: string; onDone: () => void }) {
  const [budget, setBudget] = useState(1000);
  const [maxBet, setMaxBet] = useState(Math.min(25, ceiling));
  const [stop, setStop] = useState(100);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = budget > 0 && maxBet > 0 && maxBet <= ceiling && stop > 0;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await postWithPin<PlanSummary>("/api/plans", pin, { budget, max_bet: maxBet, daily_loss_stop: stop });
      setConfirming(false);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="grid gap-5" onSubmit={(e) => { e.preventDefault(); if (valid) setConfirming(true); }}>
      <label className="block text-[15px] font-medium text-ink-strong">How much do you want to invest? ($)
        <input className={field} type="number" min={1} step={1} inputMode="numeric" value={budget} onChange={(e) => setBudget(+e.target.value)} />
      </label>
      <label className="block text-[15px] font-medium text-ink-strong">Most it may put on one bet ($)
        <input className={field} type="number" min={1} max={ceiling} step={1} inputMode="numeric" value={maxBet} onChange={(e) => setMaxBet(+e.target.value)} />
        <span className="mt-1 block text-[13px] font-normal text-ink-muted">Up to {money(ceiling)} on this server.</span>
      </label>
      <label className="block text-[15px] font-medium text-ink-strong">Stop for the day if we lose more than ($)
        <input className={field} type="number" min={1} step={1} inputMode="numeric" value={stop} onChange={(e) => setStop(+e.target.value)} />
      </label>
      {!confirming ? (
        <Button type="submit" className="h-12 text-[16px]" disabled={!valid || !pin}>{pin ? "Start investing" : "Enter the PIN above to start"}</Button>
      ) : (
        <div className="rounded-2xl bg-fill-soft p-5" role="alertdialog" aria-labelledby="confirm-text">
          <p id="confirm-text" className="text-[16px] leading-[1.5] text-ink-strong">
            This uses <b>real money</b>: up to {money(budget)} in bets of up to {money(maxBet)} each, only when the model sees an
            edge after fees. It checks every 10 minutes and stops for the day after a {money(stop)} loss.
          </p>
          <div className="mt-4 flex gap-3">
            <Button type="button" className="h-11" onClick={start} disabled={busy}>{busy ? "Starting…" : "Yes, start"}</Button>
            <Button type="button" variant="quiet" className="h-11" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {error ? <p role="alert" className="text-[14px] font-medium text-down">{error}</p> : null}
    </form>
  );
}
