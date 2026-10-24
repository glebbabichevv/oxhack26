"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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

export function EquityChart({ withCosts, withoutCosts }: { withCosts: EquityPoint[]; withoutCosts: EquityPoint[] }) {
  const data = merge(withCosts, withoutCosts);
  return (
    <div>
      <div className="h-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -14 }}>
            <CartesianGrid {...gridProps} />
            <XAxis {...xAxisProps} dataKey="t" tickFormatter={month} minTickGap={48} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => units(v)} width={56} />
            <ReferenceLine y={1} stroke={SEAM} />
            <Tooltip
              {...tooltipProps}
              labelFormatter={(t: string) => new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
              formatter={(v: number, name: string) => [units(v), name === "with" ? "after costs" : "before costs"]}
            />
            <Line type="stepAfter" dataKey="without" {...lineProps(ASH)} connectNulls />
            <Line type="stepAfter" dataKey="with" {...lineProps(INK)} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex gap-5 text-[12px] text-ink-muted">
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="2"><line x1="0" y1="1" x2="18" y2="1" stroke={INK} strokeWidth="2" /></svg>after costs</span>
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="2"><line x1="0" y1="1" x2="18" y2="1" stroke={ASH} strokeWidth="2" /></svg>before costs</span>
      </div>
    </div>
  );
}
