"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getJSON, type CalibrationHorizon } from "@/lib/api";

// The correction field: Horizon's correction as a vector field over (time to resolution, price).
// Each arrow goes from the market price p to Horizon's q(p, h), computed here from the model's four
// coefficients (GET /api/model). Dots are the test set's actual win rates (GET /api/calibration).
// The slider picks a moment; the small curve beside the field is q(p) at that moment. No fetch on drag.

type Fit = { intercept: number; coef: number[] };
type ModelJSON = { main: Fit; eps?: number };

const UP = "#15803d", DOWN = "#e11d48", INK = "#111113", ASH = "#a1a1aa";
const H_MAX = 720, H_MIN = 12, P0 = 0.03, P1 = 0.97;
const NX = 12, NY = 16;

function qOf(m: Fit, eps: number, p: number, h: number) {
  const pc = Math.min(Math.max(p, eps), 1 - eps);
  const lp = Math.log(pc / (1 - pc));
  const lh = Math.log(Math.min(Math.max(h, H_MIN), H_MAX) / 24);
  const z = m.intercept + m.coef[0] * lp + m.coef[1] * lh + m.coef[2] * lp * lh;
  return 1 / (1 + Math.exp(-z));
}
const hAt = (t: number) => H_MAX * Math.pow(H_MIN / H_MAX, t); // t: 0 = 30 days out, 1 = 12 hours out
const tOf = (h: number) => Math.log(H_MAX / h) / Math.log(H_MAX / H_MIN);
const timeLabel = (h: number) => (h >= 48 ? `${Math.round(h / 24)} days` : `${Math.round(h)} hours`);

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

export function CorrectionField({ horizons }: { horizons?: CalibrationHorizon[] }) {
  const [model, setModel] = useState<ModelJSON>();
  const [t, setT] = useState(tOf(24));
  const [ref, w] = useWidth<HTMLDivElement>();
  useEffect(() => { getJSON<ModelJSON>("/api/model").then(setModel).catch(() => undefined); }, []);

  const mobile = w < 760;
  const fieldW = mobile ? w : Math.round(w * 0.64);
  const curveW = mobile ? w : w - fieldW - 40;
  const FH = mobile ? 360 : 440;
  const m = { l: mobile ? 34 : 44, r: 10, t: 14, b: 40 };
  const x = (h: number) => m.l + tOf(h) * (fieldW - m.l - m.r);
  const y = (p: number) => m.t + (1 - (p - P0) / (P1 - P0)) * (FH - m.t - m.b);
  const eps = model?.eps ?? 0.01;

  // The field: computed once per model/size, not on drag.
  const arrows = useMemo(() => {
    if (!model || !fieldW) return [];
    const cellW = (fieldW - m.l - m.r) / NX, cellH = (FH - m.t - m.b) / NY;
    const cells: { cx: number; py: number; p: number; q: number; h: number }[] = [];
    for (let i = 0; i < NX; i++) {
      const h = hAt((i + 0.5) / NX);
      for (let j = 0; j < NY; j++) {
        const p = P0 + ((j + 0.5) / NY) * (P1 - P0);
        cells.push({ cx: x(h), py: y(p), p, q: qOf(model.main, eps, p, h), h });
      }
    }
    const maxD = Math.max(...cells.map((c) => Math.abs(c.q - c.p)), 1e-6);
    return cells.map((c) => {
      const len = ((c.q - c.p) / maxD) * 0.8 * cellH; // biggest arrow ~0.8 cell
      const s = Math.abs(len) / (0.8 * cellH);
      return { ...c, y2: c.py - len, s, up: c.q > c.p, cellW };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, fieldW, FH, eps]);

  const h = hAt(t);
  const nearest = horizons?.length ? [...horizons].sort((a, b) => Math.abs(Math.log(a.horizon_hours / h)) - Math.abs(Math.log(b.horizon_hours / h)))[0] : undefined;
  const dots = (horizons ?? []).flatMap((hz) => hz.bins.filter((b) => b.n >= 20 && b.price_mid >= P0 && b.price_mid <= P1).map((b) => ({ h: hz.horizon_hours, ...b })));
  const maxN = Math.max(1, ...dots.map((d) => d.n));

  // The side curve at the slider's moment.
  const CH = mobile ? 260 : 300, cm = { l: 34, r: 10, t: 14, b: 34 };
  const cx = (p: number) => cm.l + p * (curveW - cm.l - cm.r);
  const cy = (q: number) => cm.t + (1 - q) * (CH - cm.t - cm.b);
  const curve = model ? Array.from({ length: 61 }, (_, i) => { const p = 0.02 + (0.96 * i) / 60; return `${i ? "L" : "M"}${cx(p).toFixed(1)},${cy(qOf(model.main, eps, p, h)).toFixed(1)}`; }).join("") : "";
  const q15 = model ? qOf(model.main, eps, 0.15, h) : undefined;

  const marks = [720, 168, 72, 24, 12];
  return (
    <figure ref={ref} className="mt-12 border-t border-ink-strong pt-3">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-[15px] font-semibold text-ink-strong">The correction field</span>
        <span className="text-[12px] text-ink-faint tabular-nums">time to resolution × market price · test set out of time</span>
      </div>
      {w > 0 ? (
        <div className={mobile ? "space-y-6" : "flex items-start gap-10"}>
          <svg width={fieldW} height={FH} viewBox={`0 0 ${fieldW} ${FH}`} role="img"
            aria-label="Arrows show where Horizon moves each price: near zero a month out, growing toward the end; long shots pulled up, favourites pulled down. Dots show the test set's actual win rates.">
            {/* price grid */}
            {[0.1, 0.25, 0.5, 0.75, 0.9].map((p) => (
              <g key={p}>
                <line x1={m.l} x2={fieldW - m.r} y1={y(p)} y2={y(p)} stroke="rgba(9,9,11,0.05)" />
                <text x={m.l - 6} y={y(p) + 4} fontSize="11" fill="#71717a" textAnchor="end">{Math.round(p * 100)}¢</text>
              </g>
            ))}
            {/* the slider's moment */}
            <rect x={x(h) - (fieldW - m.l - m.r) / NX / 2} y={m.t} width={(fieldW - m.l - m.r) / NX} height={FH - m.t - m.b} fill="rgba(17,17,19,0.045)" rx={6} />
            {/* arrows: p -> q */}
            {arrows.map((a, i) => {
              const tiny = a.s < 0.12;
              const col = a.up ? UP : DOWN;
              const op = tiny ? 0.18 : 0.35 + 0.6 * a.s;
              const head = Math.min(5, Math.abs(a.y2 - a.py) * 0.6);
              const dir = a.up ? 1 : -1;
              return (
                <g key={i} stroke={col} fill={col} opacity={op}>
                  <line x1={a.cx} x2={a.cx} y1={a.py} y2={a.y2} strokeWidth={tiny ? 1 : 1.6} strokeLinecap="round" />
                  {tiny ? <circle cx={a.cx} cy={a.py} r={1.2} stroke="none" /> : (
                    <path d={`M${a.cx},${a.y2} l${-head * 0.75},${dir * head} l${head * 1.5},0 Z`} stroke="none" />
                  )}
                </g>
              );
            })}
            {/* test dots: actual win rate at (h, observed), thin line to the price bin */}
            {dots.map((d, i) => (
              <g key={`d${i}`}>
                <line x1={x(d.h) + 7} x2={x(d.h) + 7} y1={y(d.price_mid)} y2={y(Math.min(P1, Math.max(P0, d.observed)))} stroke={INK} strokeOpacity={0.25} />
                <circle cx={x(d.h) + 7} cy={y(Math.min(P1, Math.max(P0, d.observed)))} r={1.5 + 5 * Math.sqrt(d.n / maxN)} fill={INK} fillOpacity={0.55} stroke="#fff" strokeWidth={0.8} />
              </g>
            ))}
            {/* time axis: 30 days on the left, 12 hours on the right */}
            <line x1={m.l} x2={fieldW - m.r} y1={FH - m.b} y2={FH - m.b} stroke="rgba(9,9,11,0.15)" />
            {marks.map((mk, i) => (
              <text key={mk} x={x(mk)} y={FH - m.b + 16} fontSize="11" fill="#71717a" textAnchor={i === 0 ? "start" : i === marks.length - 1 ? "end" : "middle"}>{mk >= 48 ? `${mk / 24}d` : `${mk}h`}</text>
            ))}
            <text x={fieldW - m.r} y={FH - 6} fontSize="11" fill="#71717a" textAnchor="end">time to the end →</text>
          </svg>

          <div style={{ width: curveW }} className="min-w-0">
            <label className="block text-[13px] text-ink-muted">
              <span className="flex items-baseline justify-between"><span>Time to the end</span><b className="font-semibold text-ink-strong tabular-nums">{timeLabel(h)}</b></span>
              <input type="range" min={0} max={1} step={0.001} value={t} onChange={(e) => setT(Number(e.target.value))} aria-label="Time to resolution"
                className="mt-2 w-full accent-[#111113]" />
              <span className="flex justify-between text-[11px] text-ink-faint"><span>30 days</span><span>12 hours</span></span>
            </label>
            <svg width={curveW} height={CH} viewBox={`0 0 ${curveW} ${CH}`} className="mt-4" role="img" aria-label={`Horizon's probability against the market price, ${timeLabel(h)} before the end`}>
              <line x1={cx(0)} x2={cx(1)} y1={cy(0)} y2={cy(1)} stroke={ASH} strokeDasharray="4 4" />
              {[0, 0.5, 1].map((v) => (
                <g key={v}>
                  <text x={cm.l - 6} y={cy(v) + 4} fontSize="10.5" fill="#71717a" textAnchor="end">{Math.round(v * 100)}%</text>
                  <text x={cx(v)} y={CH - 16} fontSize="10.5" fill="#71717a" textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"}>{Math.round(v * 100)}¢</text>
                </g>
              ))}
              {nearest?.bins.filter((b) => b.n >= 20).map((b, i) => (
                <circle key={i} cx={cx(b.price_mid)} cy={cy(b.observed)} r={2 + 3 * Math.sqrt(b.n / Math.max(1, ...nearest.bins.map((x) => x.n)))} fill={INK} fillOpacity={0.45} />
              ))}
              <path d={curve} fill="none" stroke={INK} strokeWidth={2} />
              <text x={cx(1)} y={CH - 2} fontSize="10.5" fill="#71717a" textAnchor="end">market price</text>
            </svg>
            <p className="mt-2 text-[13px] leading-[1.55] text-ink-muted tabular-nums">
              {q15 !== undefined ? <>{timeLabel(h)} out, a 15¢ contract reads as <b className="font-semibold" style={{ color: q15 > 0.15 ? UP : DOWN }}>{Math.round(q15 * 1000) / 10}%</b>. </> : null}
              {nearest ? <>Dots: test set, {nearest.horizon_hours >= 48 ? `${nearest.horizon_hours / 24} days` : `${nearest.horizon_hours} hours`} out.</> : null}
            </p>
          </div>
        </div>
      ) : <div style={{ height: 440 }} />}
      <figcaption className="mt-3 text-[13px] text-ink-muted">Arrows: where Horizon moves the price. Dots: what actually happened out of time.</figcaption>
    </figure>
  );
}
