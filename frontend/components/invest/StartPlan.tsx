"use client";

import { useEffect, useState } from "react";
import { Button } from "@/design/components/Button";
import { money, postWithPin, type PlanSummary } from "@/lib/invest";

const field = "mt-1.5 h-12 w-full rounded-xl border border-hairline bg-white px-4 text-[18px] tabular-nums text-ink-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-strong";

// Inputs are kept as raw strings so a cleared field stays empty (invalid) instead of snapping to 0.
const num = (s: string) => (s.trim() === "" ? NaN : Number(s));

export function StartPlan({ ceiling, pin, onDone }: { ceiling: number; pin: string; onDone: () => void }) {
  const [budget, setBudget] = useState("1000");
  const [maxBet, setMaxBet] = useState(String(Math.min(25, ceiling)));
  const [stop, setStop] = useState("100");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const b = num(budget);
  const m = num(maxBet);
  const s = num(stop);
  const valid = b > 0 && m > 0 && m <= ceiling && s > 0 && Number.isFinite(b) && Number.isFinite(m) && Number.isFinite(s);

  // The server's real ceiling can arrive after mount: keep the max-per-bet inside it.
  useEffect(() => {
    setMaxBet((v) => (v.trim() === "" || Number(v) <= ceiling ? v : String(ceiling)));
  }, [ceiling]);

  // Any edit invalidates a pending confirmation, so the user always re-reads what they agreed to.
  function edit(set: (v: string) => void) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      set(e.target.value);
      setConfirming(false);
    };
  }

  async function start() {
    if (!valid || !pin) return;
    setBusy(true);
    setError(null);
    try {
      await postWithPin<PlanSummary>("/api/plans", pin, { budget: b, max_bet: m, daily_loss_stop: s });
      setConfirming(false);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="grid gap-5" onSubmit={(e) => { e.preventDefault(); if (valid && pin) setConfirming(true); }}>
      <label className="block text-[15px] font-medium text-ink-strong">How much do you want to invest? ($)
        <input className={field} type="number" min={1} step={1} inputMode="numeric" value={budget} onChange={edit(setBudget)} />
      </label>
      <label className="block text-[15px] font-medium text-ink-strong">Most it may put on one bet ($)
        <input className={field} type="number" min={1} max={ceiling} step={1} inputMode="numeric" value={maxBet} onChange={edit(setMaxBet)} />
        <span className="mt-1 block text-[13px] font-normal text-ink-muted">Up to {money(ceiling)} on this server.</span>
      </label>
      <label className="block text-[15px] font-medium text-ink-strong">Stop for the day if we lose more than ($)
        <input className={field} type="number" min={1} step={1} inputMode="numeric" value={stop} onChange={edit(setStop)} />
      </label>
      {!confirming ? (
        <Button type="submit" className="h-12 text-[16px]" disabled={!valid || !pin}>{pin ? "Start investing" : "Enter the PIN above to start"}</Button>
      ) : (
        <div className="rounded-2xl bg-fill-soft p-5" role="alertdialog" aria-labelledby="confirm-text">
          <p id="confirm-text" className="text-[16px] leading-[1.5] text-ink-strong">
            This uses <b>real money</b>: up to {money(b)} in bets of up to {money(m)} each, only when the model sees an
            edge after fees. It checks every 10 minutes and stops for the day after a {money(s)} loss.
          </p>
          <div className="mt-4 flex gap-3">
            <Button type="button" className="h-11" onClick={start} disabled={busy || !valid || !pin}>{busy ? "Starting…" : "Yes, start"}</Button>
            <Button type="button" variant="quiet" className="h-11" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {error ? <p role="alert" className="text-[14px] font-medium text-down">{error}</p> : null}
    </form>
  );
}
