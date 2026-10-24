// Recharts styling for "The Quiet Page" (DESIGN.md → Components → Charts). Spread these into Recharts props.

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
    background: "#ffffff",
    border: "1px solid rgba(9,9,11,0.08)",
    borderRadius: 12,
    boxShadow: "0 8px 28px rgba(15,23,42,0.10)",
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

/** Observed outcome rate per price bin on the calibration chart: white dot, ink ring. */
export const observedDotProps = { r: 3.5, fill: "#ffffff", stroke: INK, strokeWidth: 1.5 } as const;
/** Market = perfect calibration line (dashed Ash). */
export const marketDiagonalProps = { stroke: ASH, strokeDasharray: "5 5", strokeWidth: 2 } as const;
