"use client";

import { useEffect, useRef } from "react";

// Vertical progress line beside a sticky section head (as on our earlier landing): fills as the reader
// scrolls through the section's evidence. Writes a transform directly, no re-renders.
export function Rail() {
  const fill = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = fill.current;
    const section = el?.closest("section");
    if (!el || !section) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const r = section.getBoundingClientRect();
      const mid = window.innerHeight * 0.55;
      const p = Math.min(Math.max((mid - r.top) / Math.max(r.height, 1), 0), 1);
      el.style.transform = `scaleY(${p})`;
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); cancelAnimationFrame(raf); };
  }, []);
  return (
    <div className="absolute inset-y-1 left-0 hidden w-px bg-hairline md:block" aria-hidden>
      <div ref={fill} className="h-full w-full origin-top bg-ink-strong/60" style={{ transform: "scaleY(0)" }} />
    </div>
  );
}
