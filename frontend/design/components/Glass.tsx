"use client";
import { useEffect, useState, type HTMLAttributes, type ReactNode } from "react";

// "Glass over the Horizon" primitives (DESIGN.md → Components). React + Tailwind only.

export const UP = "#16a34a";
export const DOWN = "#e11d48";

/** Fixed three-layer backdrop. Put once at the top of the page. Image: public/backdrop.jpg. */
export function Backdrop({ src = "/backdrop.jpg" }: { src?: string }) {
  return (
    <>
      <div aria-hidden className="hz-backdrop-base" />
      <div aria-hidden className="hz-backdrop-img"><img src={src} alt="" /></div>
      <div aria-hidden className="hz-backdrop-scrim" />
    </>
  );
}

/** Glass header: full-bleed at the top, insets to a floating pill after 12px of scroll. */
export function Header({ section, right }: { section: string; right?: ReactNode }) {
  const [condensed, setCondensed] = useState(false);
  useEffect(() => {
    const onScroll = () => setCondensed(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <div className={`sticky top-0 z-40 transition-all duration-300 ${condensed ? "px-3 pt-3 sm:px-4" : ""}`}>
      <header className={`hz-glass-bar mx-auto transition-all duration-300 ${condensed ? "max-w-5xl rounded-2xl shadow-[0_8px_32px_rgba(15,23,42,0.10)]" : "max-w-full rounded-none border-x-0 border-t-0"}`}>
        <div className={`mx-auto flex h-14 items-center justify-between ${condensed ? "max-w-5xl px-4" : "max-w-[1600px] px-4 sm:px-6"}`}>
          <div className="flex items-baseline gap-2.5">
            <span className="font-display text-[19px] font-medium tracking-tight text-ink-strong">Horizon<span className="text-ink-faint">.</span></span>
            <span className="text-ink-faint">/</span>
            <span className="text-[14px] text-ink-muted">{section}</span>
          </div>
          <div className="flex items-center gap-5 text-[14px] text-ink-muted">{right}</div>
        </div>
      </header>
    </div>
  );
}

export function GlassCard({ className = "", interactive = false, ...props }: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return <div className={`hz-glass-card relative flex min-w-0 flex-col overflow-hidden rounded-card ${interactive ? "hz-glass-hover" : ""} ${className}`} {...props} />;
}

export function CardHead({ title, sub, pill }: { title: string; sub?: string; pill?: ReactNode }) {
  return (
    <div className="px-5 pt-5 sm:px-6 sm:pt-6">
      <div className="flex items-center gap-2.5">
        <h3 className="font-display text-[19px] font-semibold tracking-tight text-ink-strong">{title}</h3>
        {pill}
      </div>
      {sub ? <p className="mt-1.5 text-[14px] leading-snug text-ink-muted">{sub}</p> : null}
    </div>
  );
}

function Arrow({ up, color }: { up: boolean; color: string }) {
  return (
    <svg viewBox="0 0 12 12" className="h-3 w-3 shrink-0" fill="none" stroke={color} strokeWidth="1.9" aria-hidden>
      {up ? <path d="M1.5 8L6 3.5L10.5 8" strokeLinecap="round" strokeLinejoin="round" />
          : <path d="M1.5 4L6 8.5L10.5 4" strokeLinecap="round" strokeLinejoin="round" />}
    </svg>
  );
}

/** KPI card: label, big number, then a signed delta or a muted hint (never an empty delta). */
export function Kpi({ label, value, delta, deltaText, suffix, hint }: {
  label: string; value: string; delta?: number; deltaText?: string; suffix?: string; hint?: string;
}) {
  const color = !delta ? "rgba(9,9,11,0.45)" : delta > 0 ? UP : DOWN;
  return (
    <GlassCard interactive className="p-5 sm:p-6">
      <p className="text-[14px] text-ink-muted">{label}</p>
      <p className="mt-3 font-display text-[34px] font-semibold leading-none tracking-tight text-ink-strong tabular-nums sm:text-[40px]">{value}</p>
      {delta === undefined ? (
        <p className="mt-3 text-[13px] text-ink-muted/70">{hint ?? ""}</p>
      ) : (
        <p className="mt-3 flex items-center gap-1.5 text-[13px]">
          {delta ? <Arrow up={delta > 0} color={color} /> : null}
          <span style={{ color }} className="font-semibold tabular-nums">{deltaText}</span>
          {suffix ? <span className="text-ink-muted/70">{suffix}</span> : null}
        </p>
      )}
    </GlassCard>
  );
}

export function TrendPill({ value, up }: { value: string; up: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[13px] font-semibold tabular-nums ${up ? "bg-up-tint text-up" : "bg-down-tint text-down"}`}>
      <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
        {up ? <path d="M2 8.5L5 5.5L7 7.5L10 4M10 4H7.2M10 4V6.8" strokeLinecap="round" strokeLinejoin="round" />
            : <path d="M2 3.5L5 6.5L7 4.5L10 8M10 8H7.2M10 8V5.2" strokeLinecap="round" strokeLinejoin="round" />}
      </svg>
      {value}
    </span>
  );
}

const actionStyle = { BUY_YES: "bg-up-tint text-up", BUY_NO: "bg-down-tint text-down", NO_TRADE: "bg-ink-tint text-ink-muted" } as const;
const actionLabel = { BUY_YES: "Buy YES", BUY_NO: "Buy NO", NO_TRADE: "No trade" } as const;

export function ActionPill({ action }: { action: keyof typeof actionStyle }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[13px] font-semibold ${actionStyle[action]}`}>{actionLabel[action]}</span>;
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center rounded-full bg-ink-tint px-2.5 py-0.5 text-[12px] text-ink-muted">{children}</span>;
}

/** Pill segmented control (horizon / domain tabs). */
export function Segmented<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="inline-flex rounded-full bg-ink-tint p-[3px]">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}
          className={`rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors ${o.value === value ? "bg-white text-ink-strong shadow-[0_1px_3px_rgba(0,0,0,0.08)]" : "text-ink-muted hover:text-ink-strong"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Serif page headline with a greyed second line. */
export function SerifHeadline({ first, second }: { first: string; second?: string }) {
  return (
    <h1 className="font-serif text-[40px] leading-[1.05] tracking-[-0.02em] text-ink sm:text-[56px] lg:text-[64px]">
      {first}
      {second ? <><br /><span className="text-ink-second">{second}</span></> : null}
    </h1>
  );
}
