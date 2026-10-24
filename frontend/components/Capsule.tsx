"use client";

import { int } from "@/lib/api";

// Sealed predictions (GET /api/capsule): what we froze, its hash, and the score once opened.
// The rules were committed before the seal (capsule/EXPECTATIONS.md); the copy here restates them.

type Score = { n: number; brier_model: number; brier_market: number; gap_market_minus_model?: number; gap_ci90?: [number, number] };
type Verdict = { expected: string; n: number; verdict: string };
type Decisions = { n: number; per_dollar_kelly?: number; per_dollar_kelly_ci90?: [number, number]; hit_rate?: number };
type Opened = {
  opened_at: string; n_scored: number; n_excluded_unresolved: number; n_excluded_resolved_before_post?: number;
  primary: Tier; secondary: Tier;
  expectations?: { primary: Record<string, Verdict>; secondary: Record<string, Verdict> };
  decisions?: Decisions;
};
type Tier = { n_sealed: number; all: Score; sports: Score; crypto: Score };
export type CapsuleData = {
  seals: { name: string; sealed_at: string; deadline: string; sha256: string; timestamped: boolean; n_markets: number; n_primary?: number; opened: Opened | null }[];
  forward: null | { n_markets?: number; n_resolved?: number; brier_market?: number; brier_model?: number; trades?: { n: number; hit_rate: number; pnl_bankrolls: number } };
};

const stamp = (iso: string) => new Date(iso).toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });

function ScoreRow({ label, s }: { label: string; s: Score }) {
  if (!s.n) return null;
  const gap = s.gap_market_minus_model ?? s.brier_market - s.brier_model;
  const ci = s.gap_ci90;
  const tone = ci ? (ci[0] > 0 ? "text-up" : ci[1] < 0 ? "text-down" : "text-ink-muted") : "text-ink-muted";
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-3 border-t border-hairline-soft py-2 text-[13px] tabular-nums first:border-t-0">
      <span className="text-ink-muted">{label} <span className="text-ink-faint">n = {int(s.n)}</span></span>
      <span>
        <b className="font-semibold text-ink-strong">{s.brier_model.toFixed(4)}</b> / {s.brier_market.toFixed(4)}
        <span className={`ml-2 font-semibold ${tone}`}>
          {ci ? `${gap >= 0 ? "+" : "−"}${Math.abs(gap).toFixed(4)} [${ci[0].toFixed(4)}, ${ci[1].toFixed(4)}]` : ""}
        </span>
      </span>
    </div>
  );
}

export function Capsule({ data }: { data: CapsuleData }) {
  const seal = data.seals[0];
  if (!seal) return null;
  const o = seal.opened;
  return (
    <div className="min-w-0">
      <div className="border-t border-ink-strong pt-3">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <span className="text-[15px] font-semibold text-ink-strong">Seal 1, {stamp(seal.sealed_at)} London</span>
          <span className="text-[12px] text-ink-faint tabular-nums">{int(seal.n_markets)} markets · {int(seal.n_primary ?? 0)} primary (volume ≥ $10k)</span>
        </div>

        <dl className="grid grid-cols-[112px_1fr] gap-x-4 gap-y-2 text-[13px]">
          <dt className="text-ink-muted">SHA-256</dt>
          <dd className="min-w-0 break-all font-mono text-[12px] text-ink-strong">{seal.sha256}</dd>
          <dt className="text-ink-muted">Timestamp</dt>
          <dd className="text-ink-strong">{seal.timestamped ? "OpenTimestamps (Bitcoin calendars)" : "git commit"}</dd>
          <dt className="text-ink-muted">Opens</dt>
          <dd className="text-ink-strong">{o ? `opened ${stamp(o.opened_at)}` : `when the markets resolve, before judging (${stamp(seal.deadline)})`}</dd>
        </dl>

        <div className="mt-5 border-t border-hairline-soft pt-3">
          <div className="mb-1.5 text-[13px] font-semibold text-ink-strong">Written down before the seal</div>
          <ul className="space-y-1.5 text-[13px] leading-[1.55] text-ink-muted">
            <li>Model Brier below the market&apos;s by about 0.001 on all markets, 0.0015 on sports; no difference on crypto.</li>
            <li>That gap is about one day&apos;s sampling noise, so an inconclusive or reversed result is likely, and will be shown here as it is.</li>
            <li>Only final YES/NO resolutions count; everything else is excluded and counted. Brier, not P&amp;L, is the metric.</li>
          </ul>
        </div>

        <div className="mt-5 border-t border-hairline-soft pt-3">
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <span className="text-[13px] font-semibold text-ink-strong">Result: Brier, model / market</span>
            {o ? <span className="text-[12px] text-ink-faint tabular-nums">{int(o.n_scored)} scored · {int(o.n_excluded_unresolved)} excluded</span> : null}
          </div>
          {o ? (
            <>
              <ScoreRow label="Primary, all" s={o.primary.all} />
              <ScoreRow label="Primary, sports" s={o.primary.sports} />
              <ScoreRow label="Secondary, all" s={o.secondary.all} />
              <ScoreRow label="Secondary, sports" s={o.secondary.sports} />
              <ScoreRow label="Secondary, crypto" s={o.secondary.crypto} />
              <p className="mt-1.5 text-[12px] text-ink-faint">Green: the 90% interval of (market − model) clears zero. Grey: can&apos;t tell.</p>
              {o.expectations ? (
                <ul className="mt-3 space-y-1 text-[13px] text-ink-muted">
                  {(["all", "sports", "crypto"] as const).map((k) => {
                    const v = o.expectations!.primary[k];
                    return v ? (
                      <li key={k}>
                        <span className="text-ink-strong">Primary, {k}</span>: expected {v.expected}; <b className="font-semibold text-ink-strong">{v.verdict}</b>{" "}
                        <span className="text-ink-faint tabular-nums">(n = {int(v.n)})</span>
                      </li>
                    ) : null;
                  })}
                </ul>
              ) : null}
              {o.decisions?.n ? (
                <p className="mt-3 text-[13px] text-ink-muted tabular-nums">
                  Sealed bets, held to resolution, after fees (not the metric): {int(o.decisions.n)} bets ·{" "}
                  {o.decisions.per_dollar_kelly! >= 0 ? "+" : "−"}{Math.abs(o.decisions.per_dollar_kelly! * 100).toFixed(1)}¢ per $1
                  {o.decisions.per_dollar_kelly_ci90
                    ? ` [${(o.decisions.per_dollar_kelly_ci90[0] * 100).toFixed(0)}, ${(o.decisions.per_dollar_kelly_ci90[1] * 100).toFixed(0)}]`
                    : ""}
                  {o.n_excluded_resolved_before_post ? ` · ${int(o.n_excluded_resolved_before_post)} resolved before the hash was posted, excluded` : ""}
                </p>
              ) : null}
            </>
          ) : (
            <p className="py-3 text-[13px] text-ink-muted">Sealed and waiting. The markets resolve over the night; the score appears here, whatever it is.</p>
          )}
        </div>

        {data.forward?.trades ? (
          <div className="mt-5 border-t border-hairline-soft pt-3 text-[13px] text-ink-muted tabular-nums">
            <div className="mb-1 font-semibold text-ink-strong">Forward test: frozen trade calls</div>
            {int(data.forward.trades.n)} trades · hit rate {Math.round(data.forward.trades.hit_rate * 100)}% · P&amp;L {data.forward.trades.pnl_bankrolls >= 0 ? "+" : "−"}{Math.abs(data.forward.trades.pnl_bankrolls * 100).toFixed(1)}% of bankroll
          </div>
        ) : null}
      </div>
    </div>
  );
}
