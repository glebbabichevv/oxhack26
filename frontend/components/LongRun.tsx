"use client";

import { useEffect, useRef, useState } from "react";
import { FramedCard, Section } from "@/design/components/Page";
import { int } from "@/lib/api";

// "The long run": every headline (policy V3) test-set trade as a $1 bet, the running result after
// fees, what portfolios of 10 / 50 / 200 such bets did (event bootstrap), and the losing streaks.
// Data: public/longrun.json, written by backend/longrun.py from the same evaluate() as the backtest.

type Trade = { t: string; per_dollar: number; won: boolean; event_id: string; stake: number };
type Cum = { t: string; per_dollar: number; equal_usd: number };
type Portfolio = { n_bets: number; p5: number; p50: number; p95: number; share_up: number; share_with_20_loss_streak: number };
type LongRunData = {
  n_trades: number; hit_rate: number; per_dollar: number; per_dollar_equal: number;
  trades: Trade[]; cumulative: Cum[]; portfolios: Record<string, Portfolio>;
  streaks: { longest_losing_streak: number; streak: number; p_given_run_all_lose: number; p_streak_in_200: number; streaks_ge_20_in_test: number };
  caption: string;
};

const usd = (x: number) => Math.abs(x) < 0.005 ? "$0" : `${x < 0 ? "−" : "+"}$${Math.abs(x).toFixed(Math.abs(x) >= 100 ? 0 : 2).replace(/\.00$/, "")}`;
const cents = (x: number) => `${x >= 0 ? "+" : "−"}${Math.round(Math.abs(x) * 100)}¢`;
const pctTxt = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/** Dots per bet (green won, red lost) on two lanes under the running result of $1 per bet. */
function Strip({ d }: { d: LongRunData }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const mobile = w < 520;
  const H = mobile ? 260 : 300, lane = 14;
  const m = { l: mobile ? 44 : 56, r: 12, t: 16, b: 28 + 2 * lane + 10 };
  const t0 = Date.parse(d.trades[0]?.t ?? ""), t1 = Date.parse(d.trades[d.trades.length - 1]?.t ?? "");
  const x = (t: string) => m.l + ((Date.parse(t) - t0) / Math.max(1, t1 - t0)) * Math.max(1, w - m.l - m.r);
  const ys = d.cumulative.map((c) => c.equal_usd);
  const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys);
  const y = (v: number) => m.t + (1 - (v - lo) / Math.max(1, hi - lo)) * (H - m.t - m.b);
  const line = d.cumulative.map((c, i) => `${i ? "L" : "M"}${x(c.t).toFixed(1)},${y(c.equal_usd).toFixed(1)}`).join("");
  const laneY = H - m.b + 12;
  // $0, the top, and the low only if it doesn't collide with $0
  const ticks = [0, hi, ...(Math.abs(y(lo) - y(0)) > 16 ? [lo] : [])].filter((v, i, a) => a.indexOf(v) === i);
  const months = (() => {
    const out: { t: string; label: string }[] = [];
    const seen = new Set<string>();
    for (const tr of d.trades) {
      const dt = new Date(tr.t), k = `${dt.getUTCFullYear()}-${dt.getUTCMonth()}`;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({ t: tr.t, label: dt.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }) });
    }
    return mobile ? out.filter((_, i) => i % 2 === 0) : out;
  })();
  const last = d.cumulative[d.cumulative.length - 1];
  return (
    <div ref={ref} className="w-full">
      {w > 0 ? (
        <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img"
          aria-label={`${int(d.n_trades)} test bets of $1: ${pctTxt(d.hit_rate)} won; running result after fees ends at ${usd(last?.equal_usd ?? 0)}`}>
          {ticks.map((v) => (
            <g key={v}>
              <line x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} stroke={v === 0 ? "rgba(9,9,11,0.25)" : "rgba(9,9,11,0.06)"} strokeDasharray={v === 0 ? "3 3" : undefined} />
              <text x={m.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#71717a">{usd(v)}</text>
            </g>
          ))}
          <path d={line} fill="none" stroke="#111113" strokeWidth={1.75} strokeLinejoin="round" />
          {last ? <text x={w - m.r} y={y(last.equal_usd) - 8} textAnchor="end" fontSize="12" fontWeight={600} fill="#111113">{usd(last.equal_usd)} on {int(d.n_trades)} × $1</text> : null}
          {/* lanes: wins above, losses below */}
          <text x={m.l - 8} y={laneY + 3} textAnchor="end" fontSize="10" fill="#15803d">won</text>
          <text x={m.l - 8} y={laneY + lane + 3} textAnchor="end" fontSize="10" fill="#e11d48">lost</text>
          {d.trades.map((tr, i) => (
            <circle key={i} cx={x(tr.t)} cy={tr.won ? laneY : laneY + lane} r={1.3} fill={tr.won ? "#15803d" : "#e11d48"} fillOpacity={tr.won ? 0.75 : 0.35} />
          ))}
          {months.map((mo) => (
            <text key={mo.t} x={x(mo.t)} y={H - 6} fontSize="11" fill="#71717a" textAnchor="middle">{mo.label}</text>
          ))}
        </svg>
      ) : <div style={{ height: 260 }} />}
    </div>
  );
}

/** For each portfolio size: the 5–95% range of the total, the median, and the share that ended up. */
function Fan({ d }: { d: LongRunData }) {
  const rows = ["10", "50", "200"].map((k) => d.portfolios[k]).filter(Boolean);
  return (
    <div className="space-y-5">
      {rows.map((p) => {
        const lo = Math.min(p.p5, 0), hi = Math.max(p.p95, 0), span = Math.max(1, hi - lo);
        const at = (v: number) => `${((v - lo) / span) * 100}%`;
        return (
          <div key={p.n_bets}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
              <span className="font-semibold text-ink-strong">{p.n_bets} bets of $1</span>
              <span className="tabular-nums text-ink-muted"><b className="font-semibold text-up">{pctTxt(p.share_up)}</b> of portfolios ended up ahead</span>
            </div>
            <div className="relative mt-2 h-7">
              <div className="absolute top-1/2 h-px w-full -translate-y-1/2 bg-hairline" />
              <div className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full" style={{ left: at(p.p5), width: `calc(${at(p.p95)} - ${at(p.p5)})`, background: "linear-gradient(90deg, rgba(225,29,72,0.25), rgba(9,9,11,0.08) 50%, rgba(21,128,61,0.3))" }} />
              <div className="absolute top-0 h-full w-px bg-[rgba(9,9,11,0.35)]" style={{ left: at(0) }} />
              <div className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-ink-strong" style={{ left: at(p.p50) }} />
            </div>
            <div className="mt-1 flex justify-between text-[11px] tabular-nums text-ink-faint">
              <span>{usd(p.p5)} (bad 5%)</span>
              <span>median {usd(p.p50)}</span>
              <span>{usd(p.p95)} (good 5%)</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function LongRun() {
  const [d, setD] = useState<LongRunData>();
  useEffect(() => { fetch("/longrun.json").then((r) => (r.ok ? r.json() : undefined)).then(setD).catch(() => undefined); }, []);
  if (!d) return null;
  const s = d.streaks;
  return (
    <div id="long-run">
      <Section
        title="The long run, one bet at a time"
        lead={`Every bet the rule made on the test set, as a $1 bet: ${pctTxt(d.hit_rate)} won. Most bets lose; the winners pay several times the stake, so the total climbs only over many bets. As equal $1 bets that is ${cents(d.per_dollar_equal)} a bet after fees; with Horizon's Kelly-sized stakes, ${cents(d.per_dollar)} per $1 staked.`}
      >
        <div className="min-w-0 space-y-12">
          <FramedCard title={`Every test bet, $1 each`} meta={`${int(d.n_trades)} bets · ${pctTxt(d.hit_rate)} won · after fees`}>
            <Strip d={d} />
          </FramedCard>
          <FramedCard title="If you placed 10, 50 or 200 of them" meta="2,000 resampled portfolios (whole events)">
            <Fan d={d} />
          </FramedCard>
          <div className="border-t border-hairline pt-4 text-[14px] leading-[1.65] text-ink-muted">
            <p>
              <b className="font-semibold text-ink-strong">Losing streaks are normal here.</b> The longest in the test was{" "}
              <b className="font-semibold text-ink-strong">{s.longest_losing_streak} losses in a row</b>. Any given {s.streak} bets all lose{" "}
              {pctTxt(s.p_given_run_all_lose, 1)} of the time, but across 200 bets a {s.streak}-loss streak turns up in{" "}
              {pctTxt(s.p_streak_in_200)} of portfolios.{" "}
              {s.streaks_ge_20_in_test ? `It happened ${s.streaks_ge_20_in_test} times in the ${int(d.n_trades)} test bets.` : `In the ${int(d.n_trades)} test bets the longest run was ${s.longest_losing_streak}, so a ${s.streak}-loss run never happened.`}
              That is why each stake is a small slice of the bankroll: a quarter of the Kelly stake, at most 5%.
            </p>
            <p className="mt-3 text-[12px] text-ink-faint">{d.caption}</p>
          </div>
        </div>
      </Section>
    </div>
  );
}
