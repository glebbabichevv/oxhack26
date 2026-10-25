"use client";

import { useEffect, useRef, useState } from "react";
import { FramedCard, Hero, Nav, Section } from "@/design/components/Page";
import { CachedNote } from "@/components/CachedNote";
import { getJSON, int } from "@/lib/api";

// How we chose (GET /api/methods ← integrations/methods/summary.json): flat rows per block, one
// small chart (dot + lo–hi interval per row; a line for 'monthly') and one takeaway line each.

type Row = { block: string; name: string; value: number | null; lo?: number | null; hi?: number | null; n?: number | null; split?: string | null; note?: string | null };

const BLOCKS: { key: string; title: string; lead: string }[] = [
  { key: "monthly_coh", title: "The shipped rule, month by month", lead: "COH (one bet per event, outcome probabilities summing to 100%), refitted each month on events that ended before it. Months with fewer than 30 bets are hidden." },
  { key: "placebo_coh", title: "Placebo: if prices were right", lead: "The same 1,899 test bets, with outcomes drawn as if Polymarket's prices were exactly right, 1,000 times." },
  { key: "dsr_coh", title: "Deflated Sharpe, shipped rule", lead: "Sharpe per bet, deflated for the 12 rules we tried: the probability that the edge is not luck." },
  { key: "leg_choice", title: "Where the gain comes from", lead: "Descriptive, not used to choose: does it matter which outcome of an event we back, or only that we back one?" },
  { key: "tournament", title: "The rule tournament", lead: "Candidate rules, compared on the same trades, fees and caps, on the later half of validation. The winner was picked here; the test was opened once, for it and the earlier rule." },
  { key: "errcorr", title: "Ten models, one opinion", lead: "How alike are the models' mistakes? Correlation of errors (prediction minus outcome) for every pair, on validation. Near 1 means combining them cannot help." },
  { key: "exit", title: "When to get out", lead: "Test set: the shipped rule held to resolution, against selling earlier." },
  { key: "monthly", title: "Earlier rule V3, month by month", lead: "The rule we shipped before COH, one month at a time." },
  { key: "placebo", title: "Placebo tests, earlier rule V3", lead: "The same pipeline on outcomes where there should be nothing to find." },
  { key: "dsr", title: "Deflated Sharpe, earlier rule V3", lead: "The same luck test for the rule we shipped before COH." },
];

// Blocks whose values are returns per $1 staked: shown in cents, like the rest of the site.
const CENTS = new Set(["monthly_coh", "placebo_coh", "leg_choice", "tournament", "monthly", "placebo", "exit"]);

// Raw keys from the analysis scripts -> words a visitor can read.
const LABELS: Record<string, string> = {
  real: "Real bets", prices_are_right: "If prices were right", shuffle_within_cells: "Shuffle within price buckets",
  dsr_15_trials: "15 rules counted", dsr_4_trials: "4 rules counted", psr_test: "Sharpe > 0 (no deflation)",
  "COH real": "Real bets", "COH null": "If prices were right", "COH deflated Sharpe": "Deflated Sharpe",
  "largest-edge leg (COH)": "Largest-edge outcome (shipped)", "random eligible leg": "Random eligible outcome",
  "all eligible legs, no event cap": "Every outcome, no one-per-event",
  "V3 shipped (M0)": "V3 (earlier rule)", "V3 (shipped before)": "V3 (earlier rule)",
  "event coherence + one bet per event": "Event coherence (shipped)", "Event coherence": "Event coherence (shipped)",
  "beta calibration (Kull 2017)": "Beta calibration", "mean ensemble (8 members)": "Mean of 8 models",
  "ensemble + agreement filter": "Models agree", "time-weighted log pool": "Log pool",
  "Shin 1993 (TheMarkz3)": "Shin 1993", "power method (TheMarkz3)": "Power method", "isotonic (TheMarkz3)": "Isotonic",
  "hierarchical domain (TheMarkz3)": "Hierarchical", "exit: FIX FIX(48,12)": "Sell early (48h→12h)",
  "exit: DYNAMIC (sell when market reaches q)": "Sell when market catches up",
  COH: "Hold to resolution (shipped)", "COH+DYNAMIC": "Sell when market catches up", V3: "V3, hold", DYNAMIC: "V3, sell when caught up",
  "FIX(48,12)": "Sell early (48h→12h)",
};
const SPLITS: Record<string, string> = { val2: "validation, later half", val: "validation", test: "test, opened once", walkforward: "walk-forward", placebo: "placebo" };

const cents = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(0)}¢`;
const label = (r: Row) => LABELS[r.name] ?? r.name;

/** Rows drawn in a block's chart: summary rows out, exit shows the test rows only, plain labels. */
function chartRows(key: string, all: Row[]): Row[] {
  let rows = all.filter((r) => r.name !== "takeaway" && !/months_positive|summary|months positive/i.test(r.name));
  if (key === "monthly_coh") rows = rows.filter((r) => /COH$/.test(r.name) && (r.n ?? 0) >= 30).map((r) => ({ ...r, name: r.name.replace(/ COH$/, "") }));
  if (key === "exit") {
    const test = rows.filter((r) => / \(test\)$/.test(r.name)).map((r) => ({ ...r, name: r.name.replace(/ \(test\)$/, "") }));
    if (test.length) rows = test;
  }
  return rows.map((r) => ({ ...r, name: label(r) }));
}

/** One plain sentence per block, computed from its rows (falls back to the analysis note). */
function takeaway(key: string, all: Row[], rows: Row[]): string {
  const v = (name: string) => all.find((r) => r.name === name)?.value;
  const pos = rows.filter((r) => (r.value ?? 0) > 0).length;
  switch (key) {
    case "monthly_coh": return `Positive in ${pos} of ${rows.length} months with 30 or more bets.`;
    case "monthly": return `Positive in ${pos} of ${rows.length} months.`;
    case "placebo_coh": {
      const real = v("COH real"), nul = v("COH null");
      return real != null && nul != null ? `Real bets ${cents(real)} per $1; if prices were right, the same bets would make ${cents(nul)}. Not one of 1,000 draws did as well.` : "";
    }
    case "placebo": {
      const real = v("real"), pr = v("prices_are_right");
      return real != null && pr != null ? `Real ${cents(real)} per $1 vs ${cents(pr)} if prices were right. The within-bucket shuffle keeps each price bucket's bias by design, so it earns like the real rule; it is not the test that matters.` : "";
    }
    case "dsr_coh": { const d = v("COH deflated Sharpe"); return d != null ? `${(d * 100).toFixed(2)}% probability the edge is not luck, after counting every rule we tried.` : ""; }
    case "dsr": { const d = v("dsr_15_trials"); return d != null ? `Counting 15 rules, the earlier rule V3 does not clear the luck bar (${(d * 100).toFixed(0)}%); the shipped rule does (above).` : ""; }
    case "leg_choice": return "A random outcome of the event earns as much as the largest-edge one: the gain comes from betting once per event.";
    case "tournament": return "Event coherence won on validation; the classic de-vig models (Shin, power) call Polymarket fair and barely trade.";
    case "errcorr": {
      const lo = Math.min(...rows.map((r) => r.value ?? 1));
      return Number.isFinite(lo) ? `Every pair of models makes the same mistakes: error correlation ${lo.toFixed(3)} or higher.` : "";
    }
    case "exit": return "Hold to resolution: selling at a fixed time loses money; selling when the market catches up changes little.";
    default: return all[0]?.note ?? "";
  }
}

const fmt = (x: number) => (Math.abs(x) >= 100 ? Math.round(x).toLocaleString("en-GB") : Math.abs(x) >= 1 ? x.toFixed(2) : x.toFixed(3));

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

function extent(rows: Row[]) {
  const vals = rows.flatMap((r) => [r.value, r.lo, r.hi]).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo > 0 && lo < (hi - lo) * 0.6) lo = 0; // show zero when it is nearby
  if (hi < 0) hi = 0;
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.06;
  return [lo - pad, hi + pad] as const;
}

/** Dot + interval per row, labelled by name, on one value axis. */
function Dots({ rows, f = fmt }: { rows: Row[]; f?: (x: number) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const mobile = w < 520;
  const rowH = 30, labelW = mobile ? Math.min(150, w * 0.42) : 240, m = { r: 16, t: 8, b: 26 };
  const H = m.t + rows.length * rowH + m.b;
  const [a, b] = extent(rows);
  const x = (v: number) => labelW + ((v - a) / (b - a)) * Math.max(1, w - labelW - m.r);
  const ticks = [...new Set([a, a + (b - a) / 2, b].map((v) => Number(v.toPrecision(3))))];
  return (
    <div ref={ref} className="w-full">
      {w > 0 ? (
        <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" aria-label={rows.map((r) => `${r.name}: ${r.value ?? "n/a"}`).join("; ")}>
          {a < 0 && b > 0 ? <line x1={x(0)} x2={x(0)} y1={m.t} y2={H - m.b} stroke="rgba(9,9,11,0.3)" strokeDasharray="3 3" /> : null}
          {ticks.map((v, i) => (
            <text key={i} x={x(v)} y={H - 8} fontSize="11" fill="#71717a" textAnchor={i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle"}>{f(v)}</text>
          ))}
          {rows.map((r, i) => {
            const cy = m.t + i * rowH + rowH / 2;
            const has = typeof r.value === "number";
            return (
              <g key={`${r.name}-${i}`}>
                <line x1={labelW} x2={w - m.r} y1={cy} y2={cy} stroke="rgba(9,9,11,0.05)" />
                <text x={labelW - 10} y={cy + 4} fontSize="12" fill="#111113" textAnchor="end">{r.name.length > (mobile ? 20 : 32) ? `${r.name.slice(0, mobile ? 19 : 31)}…` : r.name}</text>
                {typeof r.lo === "number" && typeof r.hi === "number" ? (
                  <line x1={x(r.lo)} x2={x(r.hi)} y1={cy} y2={cy} stroke="#111113" strokeOpacity={0.35} strokeWidth={3} strokeLinecap="round" />
                ) : null}
                {has ? <circle cx={x(r.value as number)} cy={cy} r={4.5} fill="#111113" stroke="#fff" strokeWidth={1.5} /> : null}
                {has && !mobile ? <text x={w - m.r} y={cy - 8} fontSize="10.5" fill="#71717a" textAnchor="end">{f(r.value as number)}{r.n ? ` · n ${int(r.n)}` : ""}</text> : null}
              </g>
            );
          })}
        </svg>
      ) : <div style={{ height: H }} />}
    </div>
  );
}

/** Monthly: a line over the month names, interval as a band. */
function Line({ rows, f = fmt }: { rows: Row[]; f?: (x: number) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const H = 220, m = { l: 44, r: 12, t: 12, b: 28 };
  const pts = rows.filter((r) => typeof r.value === "number");
  const [a, b] = extent(pts);
  const x = (i: number) => m.l + (pts.length > 1 ? i / (pts.length - 1) : 0.5) * Math.max(1, w - m.l - m.r);
  const y = (v: number) => m.t + (1 - (v - a) / (b - a)) * (H - m.t - m.b);
  const line = pts.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r.value as number).toFixed(1)}`).join("");
  const band = pts.every((r) => typeof r.lo === "number" && typeof r.hi === "number")
    ? `${pts.map((r, i) => `${i ? "L" : "M"}${x(i)},${y(r.hi as number)}`).join("")}${[...pts].reverse().map((r, k) => `L${x(pts.length - 1 - k)},${y(r.lo as number)}`).join("")}Z`
    : "";
  const every = Math.max(1, Math.ceil(pts.length / Math.max(1, Math.floor((w - m.l) / 56))));
  return (
    <div ref={ref} className="w-full">
      {w > 0 && pts.length ? (
        <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" aria-label={pts.map((r) => `${r.name}: ${r.value}`).join("; ")}>
          {a < 0 && b > 0 ? <line x1={m.l} x2={w - m.r} y1={y(0)} y2={y(0)} stroke="rgba(9,9,11,0.3)" strokeDasharray="3 3" /> : null}
          {[a, b].map((v, i) => <text key={i} x={m.l - 8} y={y(v) + 4} fontSize="11" fill="#71717a" textAnchor="end">{f(Number(v.toPrecision(2)))}</text>)}
          {band ? <path d={band} fill="rgba(17,17,19,0.07)" /> : null}
          <path d={line} fill="none" stroke="#111113" strokeWidth={1.75} strokeLinejoin="round" />
          {pts.map((r, i) => <circle key={i} cx={x(i)} cy={y(r.value as number)} r={3} fill="#111113" />)}
          {pts.map((r, i) => (i % every === 0 || i === pts.length - 1 ? <text key={`l${i}`} x={x(i)} y={H - 8} fontSize="11" fill="#71717a" textAnchor={i === pts.length - 1 ? "end" : i === 0 ? "start" : "middle"}>{r.name}</text> : null))}
        </svg>
      ) : <div style={{ height: H }} />}
    </div>
  );
}

export default function MethodsPage() {
  const [rows, setRows] = useState<Row[]>();
  const [error, setError] = useState<string>();
  useEffect(() => { getJSON<{ rows: Row[] }>("/api/methods").then((d) => setRows(d.rows ?? [])).catch((e) => { setRows([]); setError(String(e)); }); }, []);
  const present = BLOCKS.filter((b) => rows?.some((r) => r.block === b.key));
  return (
    <>
      <Nav links={[{ label: "Evidence", href: "/" }, { label: "Journal", href: "/journal" }, { label: "My results", href: "/me" }, { label: "How we chose", href: "/methods" }]} />
      <main className="mx-auto max-w-[1120px] px-4 pb-24">
        <CachedNote paths={["/api/methods"]} className="mt-4" />
        <Hero
          first="How we chose the rule."
          second="And how we tried to break it."
          lead="Every check we ran on the way to the trading rule, with its interval. Where a check came out badly, it stays here."
        />
        {rows && !present.length ? (
          <p className="mt-14 border-t border-hairline pt-4 text-[15px] text-ink-muted">Results land here at 01:00.{error ? "" : ""}</p>
        ) : null}
        {present.map((b) => {
          const all = rows!.filter((r) => r.block === b.key);
          const chart = chartRows(b.key, all);
          const take = all.find((r) => r.name === "takeaway")?.note ?? takeaway(b.key, all, chart);
          const splits = [...new Set(chart.map((r) => r.split).filter(Boolean) as string[])].map((x) => SPLITS[x] ?? x).join(", ");
          const f = CENTS.has(b.key) ? cents : fmt;
          return (
            <div key={b.key} id={b.key}>
              <Section title={b.title} lead={b.lead}>
                <FramedCard title={take || undefined} meta={splits || undefined}>
                  {chart.length ? (b.key === "monthly" || b.key === "monthly_coh" ? <Line rows={chart} f={f} /> : <Dots rows={chart} f={f} />) : null}
                </FramedCard>
              </Section>
            </div>
          );
        })}
      </main>
    </>
  );
}
