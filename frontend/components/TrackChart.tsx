"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ASH, INK, SEAM, axisTick, gridProps, tooltipProps, xAxisProps } from "@/design/components/chartTheme";

// Live track record (GET /api/track): running sum of result per $1 over resolved decisions, by resolution time.
export type TrackLine = { n_resolved: number; n_open: number; total: number; mean: number | null; n_right: number; points: { t: string; cum: number; mean: number; n: number }[] };
export type Track = { journal: TrackLine; seal: (TrackLine & { name: string; n_calls: number }) | null; note: string };

const dollars = (v: number) => `${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(2)}`;
const hour = (t: number) => new Date(t).toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });

export function TrackChart({ track }: { track: Track }) {
  const j = track.journal.points.map((p) => ({ x: Date.parse(p.t), journal: p.cum }));
  const s = (track.seal?.points ?? []).map((p) => ({ x: Date.parse(p.t), seal: p.cum }));
  const data = [...j, ...s].sort((a, b) => a.x - b.x);
  if (!data.length) return <p className="py-8 text-center text-ink-muted">No resolved decisions yet.</p>;
  const line = (l: TrackLine | null | undefined, name: string) =>
    l && l.n_resolved ? `${name}: ${l.n_resolved} resolved, ${dollars(l.total)} total, ${dollars(l.mean ?? 0)} per $1 (${l.n_open} open)` : `${name}: none resolved yet${l ? ` (${l.n_open} open)` : ""}`;
  return (
    <div>
      {/* Legend with the numbers sits above the chart, one line per series, so it reads as the headline, not a footnote. */}
      <div className="mb-3 space-y-1 text-[13px] tabular-nums text-ink-muted">
        <div><span className="mr-1.5 inline-block h-[2px] w-3 align-middle" style={{ background: INK }} />{line(track.journal, "Journal decisions (before fees)")}</div>
        <div><span className="mr-1.5 inline-block h-[2px] w-3 align-middle" style={{ background: ASH }} />{line(track.seal, "Seal 1 calls (after fees)")}</div>
      </div>
      <div className="h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -6 }}>
            <CartesianGrid {...gridProps} />
            <XAxis {...xAxisProps} dataKey="x" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={hour} minTickGap={48} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => dollars(v)} width={56} />
            <ReferenceLine y={0} stroke={SEAM} />
            <Tooltip {...tooltipProps} labelFormatter={(x: number) => hour(x)}
              formatter={(v: number, name: string) => [dollars(v), name === "journal" ? "Journal, cumulative per $1" : "Seal 1, cumulative per $1"]} />
            <Line dataKey="journal" stroke={INK} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="seal" stroke={ASH} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
