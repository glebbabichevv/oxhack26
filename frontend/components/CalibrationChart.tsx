"use client";

import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { ASH, INK, axisTick, gridProps, lineProps, marketDiagonalProps, observedDotProps, tooltipProps, xAxisProps } from "@/design/components/chartTheme";
import { int, pct, type CalibrationBin } from "@/lib/api";

// Reliability chart: market = dashed diagonal, model = ink line, observed = ringed dots.
export function CalibrationChart({ bins }: { bins: CalibrationBin[] }) {
  return (
    <div>
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={bins} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid {...gridProps} />
            <XAxis
              {...xAxisProps}
              type="number"
              dataKey="price_mid"
              domain={[0, 1]}
              ticks={[0, 0.5, 1]}
              tickFormatter={(v: number) => (v === 0.5 ? "price" : `${Math.round(v * 100)}¢`)}
            />
            <YAxis type="number" domain={[0, 1]} ticks={[0, 0.5, 1]} tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} {...marketDiagonalProps} ifOverflow="visible" />
            <Tooltip
              {...tooltipProps}
              content={({ active, payload }) => {
                const b = active && payload?.[0]?.payload as CalibrationBin | undefined;
                if (!b) return null;
                return (
                  <div style={tooltipProps.contentStyle}>
                    <div style={tooltipProps.labelStyle}>Priced around {Math.round(b.price_mid * 100)}¢ · n = {int(b.n)}</div>
                    <div className="tabular-nums">Happened: <b>{pct(b.observed)}</b></div>
                    <div className="tabular-nums">Model said: <b>{pct(b.model)}</b></div>
                  </div>
                );
              }}
            />
            <Line type="monotone" dataKey="model" {...lineProps(INK)} />
            <Scatter dataKey="observed" shape={(p: { cx?: number; cy?: number }) => <circle cx={p.cx} cy={p.cy} {...observedDotProps} />} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-ink-muted">
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="2"><line x1="0" y1="1" x2="18" y2="1" stroke={ASH} strokeWidth="2" strokeDasharray="4 3" /></svg>market</span>
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="2"><line x1="0" y1="1" x2="18" y2="1" stroke={INK} strokeWidth="2" /></svg>model</span>
        <span className="inline-flex items-center gap-1.5"><svg width="9" height="9"><circle cx="4.5" cy="4.5" r="3.2" fill="#fff" stroke={INK} strokeWidth="1.3" /></svg>what actually happened</span>
      </div>
    </div>
  );
}
