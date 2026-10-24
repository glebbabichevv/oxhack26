"use client";

import { useEffect, useState } from "react";

// Rolls every number in a formatted string ("+304%", "0.1297 / 0.1305", "7,106") up from zero once,
// keeping its decimals and separators. Static under prefers-reduced-motion; screen readers get the final text.
const NUM = /\d[\d,]*(?:\.\d+)?/g;

function render(text: string, t: number) {
  return text.replace(NUM, (m) => {
    const decimals = m.split(".")[1]?.length ?? 0;
    const v = Number(m.replace(/,/g, "")) * t;
    return m.includes(",")
      ? Math.round(v).toLocaleString("en-GB")
      : v.toFixed(decimals);
  });
}

export function CountUp({ value, ms = 1100 }: { value: string; ms?: number }) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setT(1);
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const x = Math.min((now - start) / ms, 1);
      setT(1 - Math.pow(1 - x, 4)); // ease-out quart
      if (x < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return <span aria-label={value}><span aria-hidden>{render(value, t)}</span></span>;
}
