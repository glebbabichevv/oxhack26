"use client";

import { useEffect, useState } from "react";
import { FramedCard, Hero, KpiRow, Nav, Section, Segmented, DecisionRow, ActionChip } from "@/design/components/Page";
import { CalibrationChart } from "@/components/CalibrationChart";
import { EquityChart } from "@/components/EquityChart";
import {
  API_URL, cents, dateLong, getJSON, horizonLabel, horizonPhrase, horizonShort, int, pct, bankroll,
  type Backtest, type Calibration, type LiveMarket,
} from "@/lib/api";

const HORIZONS = [720, 168, 72, 24, 12] as const;
const DOMAINS = ["all", "sports", "politics", "crypto", "economics"] as const;
type Domain = (typeof DOMAINS)[number];

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-input bg-fill-soft ${className}`} />;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-10 text-center text-ink-muted">{children}</p>;
}

export default function Home() {
  const [backtest, setBacktest] = useState<Backtest>();
  const [live, setLive] = useState<LiveMarket[]>();
  const [calibration, setCalibration] = useState<Record<string, Calibration>>({});
  const [error, setError] = useState<string>();
  const [horizon, setHorizon] = useState<string>("24");
  const [domain, setDomain] = useState<Domain>("all");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    getJSON<Backtest>("/api/backtest").then(setBacktest).catch((e) => setError(String(e)));
    getJSON<LiveMarket[]>("/api/live").then(setLive).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (calibration[domain]) return;
    getJSON<Calibration>(`/api/calibration?domain=${domain}`)
      .then((c) => setCalibration((prev) => ({ ...prev, [domain]: c })))
      .catch((e) => setError(String(e)));
  }, [domain, calibration]);

  const cal = calibration[domain]?.horizons.find((h) => String(h.horizon_hours) === horizon);
  const bin15 = cal?.bins.find((b) => Math.abs(b.price_mid - 0.15) < 0.001);

  return (
    <>
      <Nav
        links={[{ label: "Live", href: "#live" }, { label: "Calibration", href: "#calibration" }, { label: "Backtest", href: "#backtest" }, { label: "Method", href: "#method" }]}
        action={<a href="#backtest" className="inline-flex h-9 items-center rounded-full bg-ink-strong px-4 text-[14px] font-medium text-white transition-colors hover:bg-[#2a2a2e]">See the backtest</a>}
      />
      <main className="mx-auto max-w-[1120px] px-4 pb-24">
        {error ? (
          <div className="mt-6 rounded-input bg-down-tint px-4 py-3 text-[13px] text-down">
            Can&apos;t reach the Horizon API at {API_URL} ({error}). Start it with <code>uvicorn app:app</code> in <code>backend/</code>.
          </div>
        ) : null}

        <Hero
          first="Polymarket prices are overconfident."
          second="Correcting them pays, in the last week."
          lead={backtest
            ? `${int(backtest.n_train_markets + backtest.n_test_markets)} resolved markets. Trained on events that ended before ${dateLong(backtest.cutoff)}, tested on the ${int(backtest.n_test_markets)} that ended after.`
            : undefined}
        />
        {backtest ? <Kpis b={backtest} /> : <Skeleton className="mt-11 h-[118px]" />}

        <div id="calibration">
          <Section
            title={bin15 ? `${horizonPhrase(Number(horizon))}, 15¢ contracts win ${pct(bin15.observed)} of the time` : "How often prices come true"}
            lead="Longshots resolve YES more often than their price says, favourites less. The model learns how far to shrink each price toward the middle, separately for each horizon."
            controls={
              <div className="flex flex-col items-start gap-3">
                <Segmented options={HORIZONS.map((h) => ({ value: String(h), label: horizonShort(h) }))} value={horizon} onChange={setHorizon} />
                <Segmented options={DOMAINS.map((d) => ({ value: d, label: d === "all" ? "All" : d[0].toUpperCase() + d.slice(1) }))} value={domain} onChange={setDomain} />
              </div>
            }
          >
            <FramedCard title={`Calibration, ${horizonLabel(Number(horizon))}`} meta={cal ? `n = ${int(cal.n)} test markets` : undefined}>
              {cal ? (
                <>
                  <CalibrationChart bins={cal.bins} />
                  <div className="mt-4 flex justify-between border-t border-hairline-soft pt-3 text-[13px] text-ink-muted tabular-nums">
                    <span>Brier, model / market</span>
                    <span>
                      <b className="font-semibold text-ink-strong">{cal.brier_model.toFixed(4)}</b> / {cal.brier_market.toFixed(4)}
                      <span className={`ml-2 font-semibold ${cal.brier_model < cal.brier_market ? "text-up" : "text-down"}`}>
                        {cal.brier_model < cal.brier_market ? "model better" : "no lift"}
                      </span>
                    </span>
                  </div>
                </>
              ) : calibration[domain] ? <Empty>No test markets at this horizon for {domain}.</Empty> : <Skeleton className="h-[290px]" />}
            </FramedCard>
          </Section>
        </div>

        <div id="live">
          <Section
            title="Live decisions"
            lead={live?.[0] ? `Open markets right now: price, model, and the call after a ${cents(live[0].cost)} cost. We only trade when the edge survives the model's own uncertainty.` : "Open markets right now: price, model, and the call after costs."}
          >
            <FramedCard>
              {live ? <LiveList live={live} showAll={showAll} onShowAll={() => setShowAll(true)} /> : <Skeleton className="h-[320px]" />}
            </FramedCard>
          </Section>
        </div>

        <div id="backtest">{backtest ? <BacktestSection b={backtest} /> : null}</div>
        {backtest ? <Failures b={backtest} /> : null}
        <div id="method">{backtest ? <Method b={backtest} /> : null}</div>

        <footer className="mt-20 border-t border-hairline pt-6 text-[12px] text-ink-faint">
          The time-to-resolution bias was measured in published research (arXiv 2602.19520). We test whether it is tradable after costs. Not investment advice.
        </footer>
      </main>
    </>
  );
}

// Horizons where the with-costs backtest makes money per trade, e.g. "12h–7d".
function payingRange(b: Backtest) {
  const paying = b.by_horizon.filter((h) => h.with_costs.mean_return_per_trade > 0).map((h) => h.horizon_hours).sort((x, y) => x - y);
  const losing = b.by_horizon.filter((h) => h.with_costs.mean_return_per_trade <= 0).map((h) => h.horizon_hours).sort((x, y) => x - y);
  return {
    value: paying.length ? `${horizonShort(paying[0])}–${horizonShort(paying[paying.length - 1])}` : "Nowhere",
    note: losing.length ? `${losing.map(horizonShort).join(", ")} out: no edge after costs` : "every horizon pays",
  };
}

function Kpis({ b }: { b: Backtest }) {
  const where = payingRange(b);
  const modelBetter = b.overall.brier_model < b.overall.brier_market;
  return (
    <KpiRow
      items={[
        {
          label: "Return after costs",
          value: bankroll(b.with_costs.return),
          note: b.return_ci ? `of bankroll · 90% CI ${bankroll(b.return_ci[0])} to ${bankroll(b.return_ci[1])}` : `max drawdown ${Math.round(b.with_costs.max_drawdown * 100)}% of bankroll`,
          tone: b.return_ci ? (b.return_ci[0] > 0 ? "up" : "down") : undefined,
        },
        { label: "Brier, model / market", value: `${b.overall.brier_model.toFixed(4)} / ${b.overall.brier_market.toFixed(4)}`, note: modelBetter ? "model better" : "no lift", tone: modelBetter ? "up" : "down" },
        { label: "Where it pays", value: where.value, note: where.note },
        { label: "Trades", value: int(b.n_trades), note: `${pct(b.with_costs.hit_rate)} hit rate, longshot-heavy` },
      ]}
    />
  );
}

function LiveList({ live, showAll, onShowAll }: { live: LiveMarket[]; showAll: boolean; onShowAll: () => void }) {
  if (!live.length) return <Empty>No open markets in the modelled price band right now.</Empty>;
  const trades = live.filter((m) => m.action !== "NO_TRADE");
  const passes = live.filter((m) => m.action === "NO_TRADE");
  const rows = showAll ? [...trades, ...passes] : [...trades.slice(0, 6), ...passes.slice(0, 3)];
  const when = (h: number) => (h >= 48 ? `${Math.round(h / 24)}d` : `${Math.max(1, Math.round(h))}h`);
  return (
    <>
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-3.5 pb-1 text-[11px] text-ink-faint">
        <span>{trades.length} trades · {passes.length} passes</span>
        <span className="text-right">price</span>
        <span className="text-right">model</span>
        <span className="w-[68px]" />
      </div>
      {rows.map((m) => (
        <DecisionRow
          key={m.market_id}
          question={m.question}
          meta={`${m.domain} · ${when(m.hours_to_resolution)}${m.action !== "NO_TRADE" ? ` · stake ${pct(m.kelly_fraction, 1)}` : ""}`}
          price={cents(m.price_yes)}
          q={pct(m.q_yes)}
          action={m.action}
          href={m.url}
          title={m.reason}
        />
      ))}
      {!showAll && rows.length < live.length ? (
        <button onClick={onShowAll} className="mt-2 w-full rounded-full bg-fill-soft py-2 text-[13px] font-medium text-ink-strong transition-colors hover:bg-black/[0.08]">
          Show all {live.length}
        </button>
      ) : null}
    </>
  );
}

function BacktestSection({ b }: { b: Backtest }) {
  const best = Math.max(...b.by_horizon.map((h) => Math.abs(h.with_costs.mean_return_per_trade)), 0.0001);
  return (
    <Section
      title={`${bankroll(b.with_costs.return)} after costs, ${bankroll(b.without_costs.return)} before`}
      lead={`Out-of-time test on ${int(b.n_test_markets)} markets, one trade per market at ¼ Kelly, P&L as a share of the starting bankroll, summed (no compounding). Always backing the favourite would have returned ${bankroll(b.naive_favourite.return)}.`}
    >
      <FramedCard title="Equity, test period" meta={`${int(b.with_costs.n_trades)} trades · max drawdown ${Math.round(b.with_costs.max_drawdown * 100)}% of bankroll`}>
        <EquityChart withCosts={b.with_costs.equity} withoutCosts={b.without_costs.equity} />
        <div className="mt-5 border-t border-hairline-soft pt-3">
          <div className="mb-2 text-[13px] font-semibold text-ink-strong">When to act: mean return per trade after costs</div>
          {[...b.by_horizon].sort((x, y) => y.horizon_hours - x.horizon_hours).map((h) => {
            const r = h.with_costs.mean_return_per_trade;
            return (
              <div key={h.horizon_hours} className="grid grid-cols-[44px_1fr_64px] items-center gap-3 py-1 text-[13px] tabular-nums">
                <span className="text-ink-muted">{horizonShort(h.horizon_hours)}</span>
                <div className="h-2 rounded-[2px] bg-fill-soft">
                  <div className={`h-2 rounded-[2px] ${r > 0 ? "bg-up" : "bg-down"}`} style={{ width: `${(Math.abs(r) / best) * 100}%` }} />
                </div>
                <span className={`text-right font-semibold ${r > 0 ? "text-up" : "text-down"}`}>{r >= 0 ? "+" : "−"}{Math.abs(r * 100).toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      </FramedCard>
    </Section>
  );
}

const KIND = { losing_domain: "Loses money", no_lift: "No lift", thin_data: "Too little data" } as const;

function Failures({ b }: { b: Backtest }) {
  const order = { losing_domain: 0, no_lift: 1, thin_data: 2 } as const;
  const failures = [...b.failures].sort((x, y) => order[x.kind] - order[y.kind]);
  return (
    <Section
      title="Where it fails"
      lead={`${b.failures.length} domain × horizon cells where the model does not beat the market or the sample is too small to say. Reported as plainly as the wins.`}
    >
      <FramedCard title="No edge here" meta={`${failures.length} cells`}>
        <div className="max-h-[300px] overflow-y-auto">
          {failures.map((f, i) => (
            <div key={i} className="flex items-center justify-between gap-3 border-t border-hairline-soft py-2.5 first:border-t-0">
              <span className="min-w-0 text-[13px]">
                <span className="font-medium capitalize">{(f.domain ?? "all").replace("_", " & ")}</span>
                <span className="text-ink-faint"> · {f.horizon_hours ? horizonShort(f.horizon_hours) : ""}</span>
                <span className="ml-2 text-ink-muted">{f.text.replace(/^[^:]+:\s*/, "")}</span>
              </span>
              <span className={`shrink-0 rounded-full px-2.5 py-[3px] text-[12px] font-semibold ${f.kind === "thin_data" ? "bg-fill-soft text-ink-muted" : "bg-down-tint text-down"}`}>{KIND[f.kind]}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 border-t border-hairline-soft pt-3">
          <div className="mb-1 text-[13px] font-semibold text-ink-strong">Worst trades in the test</div>
          {b.worst_trades.map((t, i) => (
            <div key={i} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-t border-hairline-soft py-2 text-[13px] first:border-t-0">
              <span className="min-w-0 truncate">{t.question}<span className="text-ink-faint"> · {horizonShort(t.horizon_hours)} out</span></span>
              <span className="tabular-nums text-ink-muted">{cents(t.price_yes)} → {pct(t.q_yes)}, <ActionChip action={t.action} /></span>
              <span className="w-[96px] text-right font-semibold tabular-nums text-down">{t.ret >= 0 ? "+" : "−"}{Math.round(Math.abs(t.ret) * 100)}% of stake</span>
            </div>
          ))}
        </div>
      </FramedCard>
    </Section>
  );
}

function Method({ b }: { b: Backtest }) {
  const ll = b.model_selection?.val_logloss;
  return (
    <Section
      title="How we measured it"
      lead={`Calibration map on logit(price) by horizon, chosen on a validation set${b.model_selection ? ` of ${int(b.model_selection.val_markets)} markets (picked: ${b.model_selection.chosen})` : ""}. The baseline is the market price itself.`}
    >
      <FramedCard title="Assumptions" meta={ll ? `val log loss: ${Object.entries(ll).map(([k, v]) => `${k} ${v.toFixed(4)}`).join(" · ")}` : undefined}>
        <ul className="space-y-2.5">
          {b.assumptions.map((a, i) => (
            <li key={i} className="flex gap-3 text-[13px] leading-[1.55] text-ink-muted">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-faint" />
              {a}
            </li>
          ))}
        </ul>
      </FramedCard>
    </Section>
  );
}
