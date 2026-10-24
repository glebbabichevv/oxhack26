"use client";

import { Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ASH, INK, SEAM, axisTick, gridProps, lineProps, tooltipProps, xAxisProps } from "@/design/components/chartTheme";
import type { EquityPoint } from "@/lib/api";

type Row = { t: string; with?: number; without?: number };

// The two runs have different trade dates; merge on date and carry each line forward.
function merge(withCosts: EquityPoint[], withoutCosts: EquityPoint[]): Row[] {
  const rows = new Map<string, Row>();
  for (const p of withCosts) rows.set(p.t, { ...rows.get(p.t), t: p.t, with: p.value });
  for (const p of withoutCosts) rows.set(p.t, { ...rows.get(p.t), t: p.t, without: p.value });
  const sorted = [...rows.values()].sort((a, b) => a.t.localeCompare(b.t));
  let w: number | undefined, wo: number | undefined;
  return sorted.map((r) => {
    w = r.with ?? w;
    wo = r.without ?? wo;
    return { t: r.t, with: w, without: wo };
  });
}

const month = (t: string) => new Date(t).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
const units = (v: number) => `${v >= 1 ? "+" : "−"}${Math.round(Math.abs(v - 1) * 100)}%`; // equity starts at 1 = starting bankroll

// Round ticks in starting-bankroll steps (0%, +200%, +400%…) instead of Recharts' own odd ones.
function ticksFor(rows: Row[]) {
  const vals = rows.flatMap((r) => [r.with, r.without]).filter((v): v is number => v !== undefined);
  const lo = Math.min(1, ...vals), hi = Math.max(1, ...vals);
  const step = [0.25, 0.5, 1, 2, 5].find((s) => (hi - lo) / s <= 5) ?? 10;
  const ticks: number[] = [];
  const start = lo < 1 - step / 2 ? 1 + Math.floor((lo - 1) / step) * step : 1; // no −200% tick for a 10% dip
  for (let v = start; v <= hi + step - 1e-9; v += step) ticks.push(+v.toFixed(4));
  return { ticks, lo: Math.min(start, lo) };
}

// End-of-test label: a small Ink pill at the last after-costs point.
function EndLabel({ viewBox, text }: { viewBox?: { x: number; y: number }; text: string }) {
  if (!viewBox) return null;
  const w = text.length * 7.4 + 16;
  return (
    <g transform={`translate(${viewBox.x - w + 4},${viewBox.y - 34})`}>
      <rect width={w} height={22} rx={11} fill={INK} />
      <text x={w / 2} y={15} textAnchor="middle" fill="#fff" fontSize={12} fontWeight={600} style={{ fontVariantNumeric: "tabular-nums" }}>{text}</text>
    </g>
  );
}

export function EquityChart({ withCosts, withoutCosts }: { withCosts: EquityPoint[]; withoutCosts: EquityPoint[] }) {
  const data = merge(withCosts, withoutCosts);
  const { ticks, lo } = ticksFor(data);
  const last = data[data.length - 1];
  return (
    <div>
      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -14 }}>
            <CartesianGrid {...gridProps} />
            <XAxis {...xAxisProps} dataKey="t" tickFormatter={month} minTickGap={64} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => (v === 1 ? "0%" : units(v))} width={56} ticks={ticks} domain={[lo, ticks[ticks.length - 1]]} />
            <ReferenceLine y={1} stroke={SEAM} />
            <Tooltip
              {...tooltipProps}
              labelFormatter={(t: string) => new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
              formatter={(v: number, name: string) => [units(v), name === "with" ? "after costs" : "before costs"]}
            />
            <defs>
              <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={INK} stopOpacity={0.12} />
                <stop offset="100%" stopColor={INK} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Line type="stepAfter" dataKey="without" {...lineProps(ASH)} strokeDasharray="0" connectNulls />
            <Area type="stepAfter" dataKey="with" baseValue={lo} stroke={INK} strokeWidth={2} fill="url(#eqFill)" connectNulls dot={false}
              activeDot={{ r: 3, fill: INK, stroke: "#ffffff", strokeWidth: 2 }} isAnimationActive animationDuration={1400} animationEasing="ease-out" />
            {last?.with !== undefined ? (
              <ReferenceDot x={last.t} y={last.with} r={4} fill={INK} stroke="#fff" strokeWidth={2} label={<EndLabel text={units(last.with)} />} />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex gap-5 text-[12px] text-ink-muted">
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="2"><line x1="0" y1="1" x2="18" y2="1" stroke={INK} strokeWidth="2" /></svg>after costs</span>
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="2"><line x1="0" y1="1" x2="18" y2="1" stroke={ASH} strokeWidth="2" /></svg>before costs</span>
      </div>
    </div>
  );
}
