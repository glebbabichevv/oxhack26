"use client";

import { useEffect, useRef, useState } from "react";
import { horizonShort, int, pct, type Backtest, type CalibrationHorizon } from "@/lib/api";

// The hero graphic, drawn on the page itself (no card): how often a 15¢ contract resolved YES,
// plotted against time left to resolution, with 90% binomial intervals and the 15¢ price as a rule.
// Annotated in place, newspaper-style. The line draws once, left to right; then the notes appear.

const PRICE = 0.15;
const MIN_N = 30;
const Y0 = 0.06, Y1 = 0.25;

type Pt = { h: number; p: number; lo: number; hi: number; n: number; perTrade: number | undefined };

function points(horizons: CalibrationHorizon[], b?: Backtest): Pt[] {
  return horizons
    .map((h): Pt | null => {
      const bin = h.bins.find((x) => Math.abs(x.price_mid - PRICE) < 0.001);
      if (!bin || bin.n < MIN_N) return null;
      const se = 1.645 * Math.sqrt((bin.observed * (1 - bin.observed)) / bin.n);
      const perTrade = b?.by_horizon.find((x) => x.horizon_hours === h.horizon_hours)?.with_costs.mean_return_per_trade ?? undefined;
      return { h: h.horizon_hours, p: bin.observed, lo: bin.observed - se, hi: bin.observed + se, n: bin.n, perTrade };
    })
    .filter((x): x is Pt => x !== null)
    .sort((a, b) => b.h - a.h);
}

const longName: Record<number, string> = { 720: "a month", 168: "a week", 72: "3 days", 24: "a day", 12: "12 hours" };

export function HorizonCurve({ horizons, backtest, selected, onSelect }: {
  horizons: CalibrationHorizon[]; backtest?: Backtest; selected: string; onSelect: (h: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pts = points(horizons, backtest);
  const mobile = w < 640;
  const H = mobile ? 300 : 400;
  const m = { l: mobile ? 34 : 48, r: mobile ? 18 : 150, t: 30, b: 64 };
  // log time axis: 30 days on the left, 12 hours on the right edge of the plot
  const lx = (h: number) => Math.log(h);
  const x = (h: number) => m.l + ((lx(720) - lx(h)) / (lx(720) - lx(12))) * (w - m.l - m.r);
  const y = (v: number) => m.t + (1 - (v - Y0) / (Y1 - Y0)) * (H - m.t - m.b);

  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.h).toFixed(1)},${y(p.p).toFixed(1)}`).join("");
  const gap = pts.length
    ? `${path}L${x(pts[pts.length - 1].h).toFixed(1)},${y(PRICE)}L${x(pts[0].h).toFixed(1)},${y(PRICE)}Z`
    : "";
  const first = pts[0], peak = pts.reduce<Pt | undefined>((a, p) => (!a || p.p > a.p ? p : a), undefined), last = pts[pts.length - 1];

  return (
    <figure ref={ref} className="hz-curve relative mt-12 select-none border-t border-ink-strong pt-3">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-[15px] font-semibold text-ink-strong">How often a 15¢ contract wins, by time left</span>
        <span className="text-[12px] text-ink-faint">test set, 90% intervals · tap a point to open it below</span>
      </div>
      <figcaption className="sr-only">
        How often contracts priced at 15¢ resolved YES, by time to resolution: {pts.map((p) => `${horizonShort(p.h)} ${pct(p.p)}`).join(", ")}.
      </figcaption>
      {w > 0 && pts.length ? (
        <svg width={w} height={H} className="block overflow-visible" role="img" aria-hidden>
          <defs>
            <clipPath id="above"><rect x={0} y={0} width={w} height={y(PRICE)} /></clipPath>
            <clipPath id="below"><rect x={0} y={y(PRICE)} width={w} height={H} /></clipPath>
          </defs>

          {/* y gridlines: whole percents, quiet */}
          {[0.1, 0.2].map((v) => (
            <g key={v}>
              <line x1={m.l} x2={w - m.r} y1={y(v)} y2={y(v)} stroke="rgba(9,9,11,0.06)" />
              <text x={m.l - 12} y={y(v) + 4} textAnchor="end" fontSize={11} fill="#71717a">{Math.round(v * 100)}%</text>
            </g>
          ))}

          {/* the gap between what happened and the price */}
          <path d={gap} fill="#15803d" fillOpacity={0.12} clipPath="url(#above)" className="hz-fade" />
          <path d={gap} fill="#e11d48" fillOpacity={0.1} clipPath="url(#below)" className="hz-fade" />

          {/* the price */}
          <line x1={m.l} x2={w - m.r} y1={y(PRICE)} y2={y(PRICE)} stroke="#a1a1aa" strokeWidth={1.5} strokeDasharray="5 5" />
          {!mobile ? (
            <text x={w - m.r + 14} y={y(PRICE) + 4} fontSize={13} fill="#676e7e">the price, 15¢</text>
          ) : null}

          {/* intervals */}
          {pts.map((p) => (
            <line key={`ci${p.h}`} x1={x(p.h)} x2={x(p.h)} y1={y(p.hi)} y2={y(p.lo)} stroke="#111113" strokeOpacity={0.22} strokeWidth={6} strokeLinecap="round" className="hz-fade" />
          ))}

          {/* what happened */}
          <path d={path} fill="none" stroke="#111113" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" pathLength={1} className="hz-line" />
          {pts.map((p) => {
            const on = String(p.h) === selected;
            return (
              <g key={p.h} className="cursor-pointer" onClick={() => onSelect(String(p.h))}>
                <circle cx={x(p.h)} cy={y(p.p)} r={22} fill="transparent" />
                <circle cx={x(p.h)} cy={y(p.p)} r={on ? 6.5 : 5} fill={on ? "#111113" : "#fff"} stroke="#111113" strokeWidth={2} className="hz-dot" />
              </g>
            );
          })}

          {/* x axis: time running out */}
          {pts.map((p) => (
            <g key={`x${p.h}`} className="cursor-pointer" onClick={() => onSelect(String(p.h))}>
              <text x={x(p.h)} y={H - m.b + 26} textAnchor="middle" fontSize={mobile ? 11 : 13} fontWeight={String(p.h) === selected ? 600 : 400} fill={String(p.h) === selected ? "#111113" : "#676e7e"}>
                {mobile ? horizonShort(p.h) : `${longName[p.h] ?? horizonShort(p.h)} out`}
              </text>
              {p.perTrade !== undefined && !mobile ? (
                <text x={x(p.h)} y={H - m.b + 45} textAnchor="middle" fontSize={11} fill="#71717a" style={{ fontVariantNumeric: "tabular-nums" }}>
                  {p.perTrade >= 0 ? "+" : "−"}{Math.abs(p.perTrade * 100).toFixed(1)}% a trade
                </text>
              ) : null}
            </g>
          ))}
          <line x1={m.l} x2={w - m.r} y1={H - m.b + 8} y2={H - m.b + 8} stroke="rgba(9,9,11,0.12)" />
          {!mobile ? (
            <g className="hz-note" style={{ ["--d" as string]: "1.5s" }}>
              <line x1={w - m.r} x2={w - m.r + 10} y1={H - m.b + 8} y2={H - m.b + 8} stroke="rgba(9,9,11,0.12)" />
              <path d={`M${w - m.r + 10},${H - m.b + 4}l7,4l-7,4z`} fill="rgba(9,9,11,0.35)" />
              <text x={w - m.r + 24} y={H - m.b + 12} fontSize={13} fontWeight={600} fill="#111113">resolution</text>
            </g>
          ) : null}

          {/* notes, in the page's serif */}
          {first ? (
            <g className="hz-note" style={{ ["--d" as string]: "1.2s" }}>
              <text x={x(first.h) + (mobile ? 4 : 14)} y={y(first.lo) + 26} fontFamily="var(--font-playfair), Georgia, serif" fontStyle="italic" fontSize={mobile ? 14 : 17} fill="#111113">
                A month out, about fair
              </text>
              <text x={x(first.h) + (mobile ? 4 : 14)} y={y(first.lo) + (mobile ? 44 : 46)} fontSize={12} fill="#71717a" style={{ fontVariantNumeric: "tabular-nums" }}>
                {pct(first.p)} won, n = {int(first.n)}; within noise of 15%
              </text>
            </g>
          ) : null}
          {peak && peak !== first ? (
            <g className="hz-note" style={{ ["--d" as string]: "1.6s" }}>
              <text x={x(peak.h)} y={y(peak.hi) - 16} textAnchor={mobile ? "end" : "middle"} fontFamily="var(--font-playfair), Georgia, serif" fontStyle="italic" fontSize={mobile ? 14 : 17} fill="#111113">
                {longName[peak.h] ? `${longName[peak.h][0].toUpperCase()}${longName[peak.h].slice(1)} out` : horizonShort(peak.h)}, 15¢ wins {pct(peak.p)}
              </text>
            </g>
          ) : null}
          {last && !mobile ? (
            <text x={w - m.r + 14} y={y(last.p) + 4} fontSize={13} fontWeight={600} fill="#15803d" className="hz-note" style={{ ["--d" as string]: "1.9s", fontVariantNumeric: "tabular-nums" }}>
              {pct(last.p)} won
            </text>
          ) : null}
        </svg>
      ) : (
        <div style={{ height: H }} />
      )}
    </figure>
  );
}
