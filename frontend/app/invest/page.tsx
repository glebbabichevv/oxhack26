"use client";

import { useCallback, useEffect, useState } from "react";
import { FramedCard, Hero, KpiRow, Nav, Section } from "@/design/components/Page";
import { BetsFeed } from "@/components/invest/BetsFeed";
import { PlanCard } from "@/components/invest/PlanCard";
import { ProfitChart } from "@/components/invest/ProfitChart";
import { StartPlan } from "@/components/invest/StartPlan";
import { getTrader, money, type InvestEvent, type PlansPayload, type Pnl } from "@/lib/invest";

const REFRESH_MS = 30_000;
const PIN_KEY = "horizon-dashboard-pin";

export default function InvestPage() {
  const [plans, setPlans] = useState<PlansPayload>();
  const [events, setEvents] = useState<InvestEvent[]>([]);
  const [pnl, setPnl] = useState<Pnl>();
  const [error, setError] = useState<string | null>(null);
  const [pin, setPin] = useState("");

  useEffect(() => {
    try { setPin(sessionStorage.getItem(PIN_KEY) ?? ""); } catch { /* storage blocked: ask again */ }
  }, []);

  const refresh = useCallback(async () => {
    const [p, e, n] = await Promise.allSettled([
      getTrader<PlansPayload>("/api/plans"), getTrader<InvestEvent[]>("/api/orders?limit=30"), getTrader<Pnl>("/api/pnl"),
    ]);
    if (p.status === "fulfilled") setPlans(p.value);
    if (e.status === "fulfilled") setEvents(e.value);
    if (n.status === "fulfilled") setPnl(n.value);
    if (p.status === "rejected") setError("Can't reach the trading server right now. Numbers below may be out of date.");
    else if (e.status === "rejected" || n.status === "rejected") {
      setError("Some details (recent bets or the profit chart) could not be loaded. Your plans are up to date.");
    } else setError(null);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  function savePin(v: string) {
    setPin(v);
    try { sessionStorage.setItem(PIN_KEY, v); } catch { /* keep it in memory only */ }
  }

  const all = plans?.plans ?? [];
  const invested = all.reduce((s, p) => s + p.budget, 0);
  const value = all.reduce((s, p) => s + p.value, 0);
  const cash = all.reduce((s, p) => s + p.cash, 0);
  const profit = value - invested;
  const active = all.filter((p) => p.status !== "stopped");

  return (
    <main className="mx-auto max-w-[1120px] px-4 pb-24 md:px-8">
      <Nav links={[{ label: "Model", href: "/" }, { label: "Invest", href: "/invest" }]} />
      <Hero first="Invest with the model" lead="Give it a budget. It bets only when prices look wrong after fees, spreads the money across many markets, and stops itself if things go badly." />
      {plans?.mode === "live"
        ? <p className="mt-6 inline-block rounded-full bg-down-tint px-3 py-1 text-[13px] font-semibold text-down">Real money</p>
        : plans ? <p className="mt-6 inline-block rounded-full bg-fill-soft px-3 py-1 text-[13px] font-semibold text-ink-strong">Practice mode: simulated money on live prices</p> : null}
      {error ? <p role="alert" className="mt-4 text-[15px] font-medium text-down">{error}</p> : null}

      <KpiRow items={[
        { label: "Invested", value: money(invested) },
        { label: "Now worth", value: money(value) },
        { label: "Profit", value: money(profit, true), note: invested ? `${profit >= 0 ? "+" : "−"}${Math.abs((profit / invested) * 100).toFixed(1)}%` : undefined, tone: profit > 0 ? "up" : profit < 0 ? "down" : undefined },
        { label: "Cash not yet used", value: money(cash) },
      ]} />

      <Section title="Profit so far" lead="What our real money has made, next to what the model would have made on past markets.">
        <FramedCard title="Profit in dollars">{pnl ? <ProfitChart pnl={pnl} /> : <p className="text-ink-muted">Loading…</p>}</FramedCard>
      </Section>

      <Section title="Your plans" lead="Changes need the team PIN. Looking does not.">
        <div className="grid gap-6">
          <label className="block max-w-[240px] text-[15px] font-medium text-ink-strong">Team PIN
            <input className="mt-1.5 h-12 w-full rounded-xl border border-hairline px-4 text-[18px] tracking-[0.3em] focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-strong"
              type="password" inputMode="numeric" autoComplete="off" value={pin} onChange={(e) => savePin(e.target.value)} />
          </label>
          {active.map((p) => <PlanCard key={p.id} plan={p} intervalMin={plans?.interval_min ?? 10} pin={pin} onChange={refresh} />)}
          <FramedCard title="Start investing">
            <StartPlan ceiling={plans?.max_bet_ceiling ?? 25} totalCap={plans?.max_total_exposure} mode={plans?.mode ?? "paper"} pin={pin} onDone={refresh} />
          </FramedCard>
        </div>
      </Section>

      <Section title="Recent bets" lead="Every bet, skip and settlement, newest first.">
        <FramedCard><BetsFeed events={events} /></FramedCard>
      </Section>
    </main>
  );
}
