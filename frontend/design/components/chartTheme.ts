// Recharts styling for "The Ledger" (DESIGN.md → Components → Charts). Spread these into Recharts props.

export const SEAM = "rgba(9,9,11,0.07)"; // hairline
export const INK = "#111113"; // primary series: model, with-costs equity
export const ASH = "#a1a1aa"; // secondary series: market, without-costs equity, baseline
export const UP = "#16a34a";
export const DOWN = "#e11d48";

export const axisTick = { fill: "rgba(9,9,11,0.42)", fontSize: 11 } as const;
export const xAxisProps = { tick: axisTick, tickLine: false, axisLine: false, dy: 6 } as const;
export const gridProps = { stroke: SEAM, vertical: false } as const;

export const tooltipProps = {
  contentStyle: {
    background: "rgba(255,255,255,0.72)",
    backdropFilter: "blur(26px) saturate(200%)",
    WebkitBackdropFilter: "blur(26px) saturate(200%)",
    border: "1px solid rgba(255,255,255,0.6)",
    borderRadius: 12,
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.85), 0 8px 28px rgba(0,0,0,0.10)",
    padding: "7px 11px",
    fontSize: 12,
    color: "#0a0a0a",
  },
  labelStyle: { color: "rgba(9,9,11,0.5)", marginBottom: 2 },
  cursor: { stroke: "rgba(9,9,11,0.18)" },
} as const;

/** Bars: put <BarGradient /> inside <defs>, then fill="url(#barFill)" radius={[2,2,0,0]}. */
export const barGradientStops = [
  { offset: "0%", stopColor: "#3f3f46" },
  { offset: "100%", stopColor: "#a1a1aa" },
] as const;

/** Lines: 2px, no dots, white-ringed active dot. type "stepAfter" for equity, "monotone" for calibration. */
export const lineProps = (color: string) => ({
  stroke: color,
  strokeWidth: 2,
  dot: false,
  activeDot: { r: 3, fill: color, stroke: "#ffffff", strokeWidth: 2 },
  isAnimationActive: false,
});

/** Perfect-calibration diagonal on the reliability chart. */
export const diagonalProps = { stroke: SEAM, strokeDasharray: "4 4", strokeWidth: 1 } as const;

export const CHART_HEIGHT = 240;
