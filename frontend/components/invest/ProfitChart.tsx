"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ASH, INK, SEAM, axisTick, gridProps, tooltipProps, xAxisProps } from "@/design/components/chartTheme";
import { money, type Pnl } from "@/lib/invest";

type Row = { t: string; real?: number; backtest?: number };

// Real points are timestamps, backtest points are dates: merge on the day, carry each line forward.
function merge(pnl: Pnl): Row[] {
  const rows = new Map<string, Row>();
  for (const p of pnl.backtest) rows.set(p.t.slice(0, 10), { ...rows.get(p.t.slice(0, 10)), t: p.t.slice(0, 10), backtest: p.value });
  for (const p of pnl.real) rows.set(p.t.slice(0, 10), { ...rows.get(p.t.slice(0, 10)), t: p.t.slice(0, 10), real: p.value });
  let b: number | undefined;
  return [...rows.values()].sort((x, y) => x.t.localeCompare(y.t)).map((r) => {
    b = r.backtest ?? b;
    return { ...r, backtest: b };
  });
}

const day = (t: string) => new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export function ProfitChart({ pnl }: { pnl: Pnl }) {
  const data = merge(pnl);
  return (
    <figure>
      <div className="h-[300px]" role="img" aria-label={`Profit chart. Real money so far: ${money(pnl.real.at(-1)?.value ?? 0, true)}. Model test since May, after costs, on ${money(pnl.backtest_budget)}: ${money(pnl.backtest.at(-1)?.value ?? 0, true)}.`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
            <CartesianGrid {...gridProps} />
            <XAxis {...xAxisProps} dataKey="t" tickFormatter={day} minTickGap={48} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} width={64} tickFormatter={(v: number) => money(v, true)} />
            <ReferenceLine y={0} stroke={SEAM} />
            <Tooltip {...tooltipProps} labelFormatter={day}
              formatter={(v: number, name: string) => [money(v, true), name === "real" ? "Our real money" : "Model test (after costs)"]} />
            <Line dataKey="backtest" stroke={ASH} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="real" stroke={INK} strokeWidth={2.5} dot={{ r: 2.5, fill: INK }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-ink-muted">
        <span className="inline-flex items-center gap-2"><svg width="20" height="3" aria-hidden><line x1="0" y1="1.5" x2="20" y2="1.5" stroke={INK} strokeWidth="2.5" /></svg>Our real money</span>
        <span className="inline-flex items-center gap-2"><svg width="20" height="3" aria-hidden><line x1="0" y1="1.5" x2="20" y2="1.5" stroke={ASH} strokeWidth="2" strokeDasharray="5 4" /></svg>If we'd followed the model since May (test, after costs, on {money(pnl.backtest_budget)})</span>
      </figcaption>
      <p className="mt-2 text-[13px] text-ink-faint">The dashed line is a test on past markets, not money we made. The solid line is real.</p>
    </figure>
  );
}
