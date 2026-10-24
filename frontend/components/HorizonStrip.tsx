"use client";

import { horizonShort, int, pct, type Backtest, type CalibrationHorizon } from "@/lib/api";

// The page's one authored moment: the same 15¢ contract on a time axis, 30 days out → 12 hours out.
// The axis draws left to right, then each column's bar rises in turn: the bias appears as time runs out.
// A column is coloured only when the gap to the price is outside sampling noise (90%, binomial).

const PRICE = 0.15;
const SCALE = 0.25; // bar height = observed / SCALE
const MIN_N = 30;

type Col = { h: number; observed?: number; n: number; signal: "up" | "down" | "fair" | "thin"; perTrade?: number };

function columns(horizons: CalibrationHorizon[], b?: Backtest): Col[] {
  return [...horizons].sort((x, y) => y.horizon_hours - x.horizon_hours).map((h) => {
    const bin = h.bins.find((x) => Math.abs(x.price_mid - PRICE) < 0.001);
    const perTrade = b?.by_horizon.find((x) => x.horizon_hours === h.horizon_hours)?.with_costs.mean_return_per_trade;
    if (!bin || bin.n < MIN_N) return { h: h.horizon_hours, n: bin?.n ?? 0, signal: "thin", perTrade };
    const noise = 1.645 * Math.sqrt((PRICE * (1 - PRICE)) / bin.n);
    const gap = bin.observed - PRICE;
    const signal = Math.abs(gap) < noise ? "fair" : gap > 0 ? "up" : "down";
    return { h: h.horizon_hours, observed: bin.observed, n: bin.n, signal, perTrade };
  });
}

const tone = { up: "text-up", down: "text-down", fair: "text-ink-muted", thin: "text-ink-faint" } as const;
const bar = { up: "bg-up", down: "bg-down", fair: "bg-[#a1a1aa]", thin: "bg-fill-soft" } as const;
const verdict = { up: "wins more than priced", down: "wins less than priced", fair: "≈ fair, within noise", thin: "too few to say" } as const;
const short = { up: "cheap", down: "pricey", fair: "≈ fair", thin: "few" } as const;

export function HorizonStrip({ horizons, backtest, selected, onSelect }: {
  horizons: CalibrationHorizon[]; backtest?: Backtest; selected: string; onSelect: (h: string) => void;
}) {
  const cols = columns(horizons, backtest);
  return (
    <div className="hz-strip mt-12 rounded-frame bg-frame p-2 shadow-frame">
      <div className="rounded-card border border-hairline-soft bg-page px-5 pb-4 pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <span className="text-[15px] font-semibold text-ink-strong">The same 15¢ contract, as resolution approaches</span>
          <span className="text-[12px] text-ink-faint">how often it actually resolved YES · test set · tap a horizon</span>
        </div>

        {/* Time axis: a hairline that draws itself left → right, ending at "resolution". */}
        <div className="hz-axis relative mt-5 flex items-center gap-2 text-[12px] font-medium text-ink-muted" aria-hidden>
          <span>a month out</span>
          <div className="h-px flex-1 bg-gradient-to-r from-ink-strong/10 to-ink-strong/50" />
          <svg width="7" height="9" viewBox="0 0 7 9" className="-ml-2 text-ink-strong/50"><path d="M0 0l7 4.5L0 9z" fill="currentColor" /></svg>
          <span className="text-ink-strong">resolution</span>
        </div>

        <div role="radiogroup" aria-label="Time to resolution" className="mt-3 grid grid-cols-5 gap-1.5 md:gap-3">
          {cols.map((c, i) => {
            const active = String(c.h) === selected;
            const height = c.observed !== undefined ? Math.min(c.observed / SCALE, 1) * 100 : 6;
            return (
              <button
                key={c.h}
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={`${horizonShort(c.h)} out: ${c.observed !== undefined ? pct(c.observed) : "n/a"}, ${verdict[c.signal]}`}
                onClick={() => onSelect(String(c.h))}
                style={{ ["--i" as string]: i }}
                className={`group relative flex flex-col items-start rounded-input px-1.5 pb-2 pt-3 text-left transition-colors duration-200 md:px-3 ${active ? "bg-fill-soft" : "hover:bg-black/[0.025]"}`}
              >
                <span className="text-[12px] font-medium text-ink-muted">{horizonShort(c.h)}<span className="hidden md:inline"> out</span></span>
                <span className={`mt-1 text-[22px] font-semibold leading-none tracking-[-0.02em] tabular-nums md:text-[34px] ${c.signal === "thin" ? "text-ink-faint" : "text-ink-strong"}`}>
                  {c.observed !== undefined ? pct(c.observed) : "–"}
                </span>

                {/* Bar on a 0–25% scale, with the 15¢ price as a dashed rule across it. */}
                <div className="relative mt-3 h-[84px] w-full border-b border-hairline md:h-[112px]">
                  <div className="absolute inset-x-0 border-t border-dashed border-[#a1a1aa]" style={{ bottom: `${(PRICE / SCALE) * 100}%` }} />
                  <div className={`hz-bar absolute bottom-0 left-1/2 w-[46%] max-w-[44px] -translate-x-1/2 rounded-t-[3px] ${bar[c.signal]}`} style={{ height: `${height}%` }} />
                </div>

                <span className={`mt-2 text-[11px] font-semibold leading-tight md:text-[12px] ${tone[c.signal]}`}><span className="md:hidden">{short[c.signal]}</span><span className="hidden md:inline">{verdict[c.signal]}</span></span>
                {c.perTrade !== undefined ? (
                  <span className="mt-0.5 hidden text-[12px] tabular-nums text-ink-faint md:block">
                    trade return <b className={`font-semibold ${c.perTrade > 0 ? "text-up" : "text-down"}`}>{c.perTrade >= 0 ? "+" : "−"}{Math.abs(c.perTrade * 100).toFixed(1)}%</b>
                  </span>
                ) : null}
                <span className="mt-0.5 hidden text-[11px] tabular-nums text-ink-faint md:block">n = {int(c.n)}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex items-center gap-2 border-t border-hairline-soft pt-3 text-[12px] text-ink-muted">
          <svg width="18" height="2" aria-hidden><line x1="0" y1="1" x2="18" y2="1" stroke="#a1a1aa" strokeWidth="1.5" strokeDasharray="3 3" /></svg>
          the price: 15¢ = a 15% chance
        </div>
      </div>
    </div>
  );
}
