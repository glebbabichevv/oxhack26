"use client";

import { useEffect, useState } from "react";
import { FramedCard, Hero, KpiRow, Nav, Section, Segmented, DecisionRow, ActionChip, EdgeTrack } from "@/design/components/Page";
import { HorizonCurve } from "@/components/HorizonCurve";
import { Capsule, type CapsuleData } from "@/components/Capsule";
import { CalibrationChart } from "@/components/CalibrationChart";
import { EquityChart } from "@/components/EquityChart";
import {
  API_URL, cents, dateLong, getJSON, horizonLabel, horizonPhrase, horizonShort, int, pct, bankroll,
  type Backtest, type Calibration, type LiveMarket, type LivePayload,
} from "@/lib/api";

const LIVE_REFRESH_MS = 2 * 60 * 1000;

function ago(iso: string | null | undefined, now: number) {
  if (!iso) return "time unknown";
  const min = Math.max(0, Math.round((now - Date.parse(iso)) / 60000));
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

function Freshness({ meta, now }: { meta?: LivePayload; now: number }) {
  if (!meta) return null;
  const live = meta.source === "live";
  return (
    <p className="text-[12px] text-ink-faint tabular-nums" title={meta.error}>
      {live ? "Live" : "Saved snapshot (live feed unavailable)"} · updated {ago(meta.updated_at, now)}
      {meta.model_version ? ` · model ${meta.model_version}` : ""}
    </p>
  );
}

const HORIZONS = [720, 168, 72, 24, 12] as const;
const DOMAINS = ["all", "sports", "politics", "crypto", "economics"] as const;
type Domain = (typeof DOMAINS)[number];
const MIN_BIN = 30; // same floor the backend uses for "too few to trust"
const TIE = 0.0005; // Brier gaps smaller than this are not worth calling

// "model better by 0.0007" / "about equal" / "no lift": the gap, not just its sign.
function brierVerdict(model: number, market: number) {
  const gap = market - model;
  if (gap >= TIE) return { text: `model better by ${gap.toFixed(4)}`, tone: "up" as const };
  if (gap > 0) return { text: "about equal", tone: undefined };
  return { text: "no lift", tone: "down" as const };
}

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-input bg-fill-soft ${className}`} />;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-10 text-center text-ink-muted">{children}</p>;
}

export default function Home() {
  const [backtest, setBacktest] = useState<Backtest>();
  const [live, setLive] = useState<LiveMarket[]>();
  const [liveMeta, setLiveMeta] = useState<LivePayload>();
  const [now, setNow] = useState(() => Date.now());
  const [calibration, setCalibration] = useState<Record<string, Calibration>>({});
  const [error, setError] = useState<string>();
  const [horizon, setHorizon] = useState<string>("24");
  const [domain, setDomain] = useState<Domain>("all");
  const [showAll, setShowAll] = useState(false);
  const [capsule, setCapsule] = useState<CapsuleData>();

  useEffect(() => {
    getJSON<Backtest>("/api/backtest").then(setBacktest).catch((e) => setError(String(e)));
    getJSON<CapsuleData>("/api/capsule").then(setCapsule).catch(() => undefined); // optional section
  }, []);

  // Live decisions: fetched now, then every 2 min while the tab is visible (the API recomputes every ~5 min).
  useEffect(() => {
    const load = () =>
      getJSON<LivePayload | LiveMarket[]>("/api/live")
        .then((d) => {
          const payload: LivePayload = Array.isArray(d) ? { updated_at: null, model_version: null, source: "fallback", markets: d } : d;
          setLive(payload.markets);
          setLiveMeta(payload);
        })
        .catch((e) => setError(String(e)));
    load();
    const poll = setInterval(() => { if (document.visibilityState === "visible") load(); }, LIVE_REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 30_000);
    const onVisible = () => { if (document.visibilityState === "visible") { setNow(Date.now()); load(); } };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(poll); clearInterval(tick); document.removeEventListener("visibilitychange", onVisible); };
  }, []);

  useEffect(() => {
    if (calibration[domain]) return;
    getJSON<Calibration>(`/api/calibration?domain=${domain}`)
      .then((c) => setCalibration((prev) => ({ ...prev, [domain]: c })))
      .catch((e) => setError(String(e)));
  }, [domain, calibration]);

  const cal = calibration[domain]?.horizons.find((h) => String(h.horizon_hours) === horizon);
  const bin15 = cal?.bins.find((b) => Math.abs(b.price_mid - 0.15) < 0.001);
  const domainWord = domain === "all" ? "" : `${domain} `;
  const brier = cal ? brierVerdict(cal.brier_model, cal.brier_market) : undefined;

  return (
    <>
      <Nav
        links={[{ label: "Calibration", href: "#calibration" }, { label: "Live", href: "#live" }, { label: "Sealed", href: "#sealed" }, { label: "Backtest", href: "#backtest" }, { label: "Method", href: "#method" }]}
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
          second="Correcting them pays, most near resolution."
          lead={backtest
            ? `Trained on ${int(backtest.n_train_markets)} resolved Polymarket markets that ended before ${dateLong(backtest.cutoff)}; tested out of time on the ${int(backtest.n_test_markets)} that ended after.`
            : undefined}
        />
        {calibration.all ? (
          <HorizonCurve horizons={calibration.all.horizons} backtest={backtest} selected={horizon} onSelect={setHorizon} />
        ) : <div className="mt-14 h-[400px]" />}
        {backtest ? <Kpis b={backtest} /> : <Skeleton className="mt-11 h-[118px]" />}

        <div id="calibration">
          <Section
            title={bin15 && bin15.n >= MIN_BIN
              ? `${horizonPhrase(Number(horizon))}, 15¢ ${domainWord}contracts win ${pct(bin15.observed)} of the time`
              : bin15
                ? `${horizonPhrase(Number(horizon))}, too few 15¢ ${domainWord}contracts to say`
                : "How often prices come true"}
            lead={`${bin15 && bin15.n >= MIN_BIN
              ? `Here, contracts priced near 15¢ resolve YES ${bin15.observed > 0.15 ? "more" : "less"} often than their price says. `
              : ""}The model learns how far to move each price, separately for each horizon; the dots show what actually happened. Pick how far from resolution, and which kind of market.`}
            controls={
              <div className="flex flex-col items-start gap-4">
                <Segmented label="Time to resolution" options={HORIZONS.map((h) => ({ value: String(h), label: horizonShort(h) }))} value={horizon} onChange={setHorizon} />
                <Segmented label="Market type" options={DOMAINS.map((d) => ({ value: d, label: d === "all" ? "All" : d[0].toUpperCase() + d.slice(1) }))} value={domain} onChange={setDomain} />
              </div>
            }
          >
            <FramedCard
              title={`Calibration${domain === "all" ? "" : `, ${domain}`}, ${horizonLabel(Number(horizon))}`}
              meta={cal ? `n = ${int(cal.n)} test markets${bin15 ? ` · ${int(bin15.n)} near 15¢` : ""}` : undefined}
            >
              {cal ? (
                <>
                  <CalibrationChart bins={cal.bins} />
                  <div className="mt-4 flex flex-wrap justify-between gap-x-4 gap-y-1 border-t border-hairline-soft pt-3 text-[13px] text-ink-muted tabular-nums">
                    <span>Brier score, model / market <span className="text-ink-faint">(lower is better)</span></span>
                    <span>
                      <b className="font-semibold text-ink-strong">{cal.brier_model.toFixed(4)}</b> / {cal.brier_market.toFixed(4)}
                      <span className={`ml-2 font-semibold ${brier!.tone === "up" ? "text-up" : brier!.tone === "down" ? "text-down" : "text-ink-muted"}`}>{brier!.text}</span>
                    </span>
                  </div>
                </>
              ) : calibration[domain] ? <Empty>No {domainWord}test markets at this horizon.</Empty> : <Skeleton className="h-[290px]" />}
            </FramedCard>
          </Section>
        </div>

        <div id="live">
          <Section
            title="Live decisions"
            lead={live?.[0] ? "Open markets right now: price, model, and the call after the spread and Polymarket's fee. We only trade when the edge survives the model's own uncertainty." : "Open markets right now: price, model, and the call after costs."}
            controls={<Freshness meta={liveMeta} now={now} />}
          >
            <FramedCard>
              {live ? <LiveList live={live} showAll={showAll} onToggle={() => setShowAll((s) => !s)} /> : <Skeleton className="h-[320px]" />}
            </FramedCard>
          </Section>
        </div>

        {capsule?.seals.length ? (
          <div id="sealed">
            <Section
              title="Sealed before the outcomes"
              lead="A backtest can always be tuned after the fact. So on Saturday afternoon we hashed Horizon's probabilities for every market that ends before judging, after writing down how they would be scored and what we expected. It opens on Sunday, whatever it says."
            >
              <Capsule data={capsule} />
            </Section>
          </div>
        ) : null}

        <div id="backtest">{backtest ? <BacktestSection b={backtest} /> : null}</div>
        {backtest ? <Failures b={backtest} /> : null}
        <div id="method">{backtest ? <Method b={backtest} /> : null}</div>

        <footer className="mt-20 border-t border-hairline pt-6 text-[12px] text-ink-faint">
          The time-to-resolution bias was measured in published research (<a href="https://arxiv.org/abs/2602.19520" target="_blank" rel="noreferrer" className="underline decoration-hairline underline-offset-4 hover:text-ink-muted">arXiv 2602.19520</a>). We test whether it is tradable after costs. Not investment advice.
        </footer>
      </main>
    </>
  );
}

const MIN_DOMAIN_TRADES = 100; // below this a domain's CI is too wide to headline

const domainName = (d: string) => (d[0].toUpperCase() + d.slice(1)).replace("_", " & ");

// Market types whose with-costs return CI clears zero on a real sample, e.g. "Sports".
function whereItPays(b: Backtest) {
  const clear = (b.by_domain ?? []).filter((d) => d.n_trades >= MIN_DOMAIN_TRADES && d.return_ci && d.return_ci[0] > 0);
  if (!clear.length) return { value: "Nowhere clear", note: "no market type's CI clears zero" };
  const top = clear[0];
  return {
    value: clear.map((d) => domainName(d.domain)).join(", "),
    note: `${bankroll(top.return)}, CI ${bankroll(top.return_ci![0])} to ${bankroll(top.return_ci![1])}; other types' CIs include 0`,
  };
}

function Kpis({ b }: { b: Backtest }) {
  const where = whereItPays(b);
  const brier = brierVerdict(b.overall.brier_model, b.overall.brier_market);
  // Headline = the honest variant: fees on, and never more than one bankroll staked at once.
  const head = b.capped_exposure ?? { ...b.with_costs, return_ci: b.return_ci };
  return (
    <KpiRow
      items={[
        {
          label: "Return after fees and spread",
          value: bankroll(head.return),
          note: head.return_ci ? `of bankroll${b.capped_exposure ? ", ≤1 bankroll at risk" : ""} · 90% CI ${bankroll(head.return_ci[0])} to ${bankroll(head.return_ci[1])}` : `max drawdown ${Math.round(head.max_drawdown * 100)}% of bankroll`,
          tone: head.return_ci ? (head.return_ci[0] > 0 ? "up" : "down") : undefined,
        },
        { label: "Brier score, model", value: b.overall.brier_model.toFixed(4), note: `vs market ${b.overall.brier_market.toFixed(4)} · lower is better`, tone: brier.tone },
        { label: "Where it pays", value: where.value, note: where.note },
        { label: "Trades", value: int(b.n_trades), note: `${pct(b.with_costs.hit_rate)} hit rate, longshot-heavy` },
      ]}
    />
  );
}

function LiveList({ live, showAll, onToggle }: { live: LiveMarket[]; showAll: boolean; onToggle: () => void }) {
  if (!live.length) return <Empty>No open markets in the modelled price band right now.</Empty>;
  const trades = live.filter((m) => m.action !== "NO_TRADE");
  const passes = live.filter((m) => m.action === "NO_TRADE");
  const rows = showAll ? [...trades, ...passes] : [...trades.slice(0, 6), ...passes.slice(0, 3)];
  const when = (h: number) => (h >= 48 ? `${Math.round(h / 24)}d` : `${Math.max(1, Math.round(h))}h`);
  return (
    <>
      <div className="grid grid-cols-[1fr_auto_auto_auto] gap-3.5 pb-1 text-[12px] text-ink-faint md:grid-cols-[1fr_auto_120px_auto_auto]">
        <span>{trades.length} trades · {passes.length} passes</span>
        <span className="hidden text-right md:block">market</span>
        <span className="hidden text-center md:block">price → model</span>
        <span className="hidden text-right md:block">model</span>
        <span className="hidden w-[68px] md:block" />
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
          track={<EdgeTrack price={m.price_yes} q={m.q_yes} lo={m.q_low} hi={m.q_high} action={m.action} />}
        />
      ))}
      {live.length > 9 ? (
        <button type="button" onClick={onToggle} aria-expanded={showAll} className="mt-2 min-h-9 w-full rounded-full bg-fill-soft py-2 text-[13px] font-medium text-ink-strong transition-colors duration-150 hover:bg-black/[0.08]">
          {showAll ? "Show fewer" : `Show all ${live.length}`}
        </button>
      ) : null}
    </>
  );
}

function BacktestSection({ b }: { b: Backtest }) {
  const best = Math.max(...b.by_horizon.map((h) => Math.abs(h.with_costs.mean_return_per_trade)), 0.0001);
  return (
    <Section
      title={`After fees and spread, the test made ${bankroll((b.capped_exposure ?? b.with_costs).return)} of its starting bankroll`}
      lead={`Out-of-time test on ${int(b.n_test_markets)} markets, one trade per market at ¼ Kelly, P&L as a share of the starting bankroll, summed (no compounding)${b.capped_exposure ? `, with at most one bankroll staked at once. Uncapped, open stakes peaked at ${b.peak_open_stake?.toFixed(2)} bankrolls and it made ${bankroll(b.with_costs.return)}; per $1 staked, ${bankroll(b.return_per_dollar_staked ?? 0)}` : ""}. Before costs it would have been ${bankroll(b.without_costs.return)}; always backing the favourite would have returned ${bankroll(b.naive_favourite.return)}.`}
    >
      <FramedCard title="Equity, test period, uncapped stakes" meta={`${int(b.with_costs.n_trades)} trades · max drawdown ${Math.round(b.with_costs.max_drawdown * 100)}% of bankroll`}>
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
        {b.by_domain?.length ? <DomainReturns rows={b.by_domain} /> : null}
      </FramedCard>
    </Section>
  );
}

// Return after costs per market type with its 90% CI: a range bar around zero, dot at the estimate.
function DomainReturns({ rows }: { rows: NonNullable<Backtest["by_domain"]> }) {
  const shown = rows.filter((d) => d.n_trades >= 30 && d.return_ci);
  const lo = Math.min(0, ...shown.map((d) => d.return_ci![0]));
  const hi = Math.max(...shown.map((d) => d.return_ci![1]), 0.01);
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <div className="mt-5 border-t border-hairline-soft pt-3">
      <div className="mb-2 text-[13px] font-semibold text-ink-strong">Where: return after costs by market type, with 90% CI</div>
      {shown.map((d) => {
        const clear = d.return_ci![0] > 0;
        return (
          <div key={d.domain} className="grid grid-cols-[112px_1fr_64px] items-center gap-3 py-1 text-[13px] tabular-nums">
            <span className="truncate text-ink-muted" title={`${int(d.n_trades)} trades`}>{domainName(d.domain)}</span>
            <div className="relative h-2" aria-label={`${bankroll(d.return)}, 90% CI ${bankroll(d.return_ci![0])} to ${bankroll(d.return_ci![1])}`}>
              <div className="absolute inset-y-0 w-px bg-hairline" style={{ left: x(0) }} />
              <div className={`absolute inset-y-0 rounded-[2px] ${clear ? "bg-up-tint" : "bg-fill-soft"}`} style={{ left: x(d.return_ci![0]), right: `calc(100% - ${x(d.return_ci![1])})` }} />
              <div className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white ${clear ? "bg-up" : "bg-ink-faint"}`} style={{ left: x(d.return) }} />
            </div>
            <span className={`text-right font-semibold ${clear ? "text-up" : "text-ink-muted"}`}>{bankroll(d.return)}</span>
          </div>
        );
      })}
      <p className="mt-1.5 text-[12px] text-ink-faint">Green: the interval clears zero. Grey: can&apos;t tell from this sample.</p>
    </div>
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
            <div key={i} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 border-t border-hairline-soft py-2 text-[13px] first:border-t-0 md:grid-cols-[1fr_auto_auto]">
              <span className="col-span-2 min-w-0 md:col-span-1 md:truncate" title={t.question}>{t.question}<span className="text-ink-faint"> · {horizonShort(t.horizon_hours)} out</span></span>
              <span className="tabular-nums text-ink-muted">{cents(t.price_yes)} → {pct(t.q_yes)} <ActionChip action={t.action} /></span>
              <span className="whitespace-nowrap text-right font-semibold tabular-nums text-down">{t.ret >= 0 ? "+" : "−"}{Math.round(Math.abs(t.ret) * 100)}% of stake</span>
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
