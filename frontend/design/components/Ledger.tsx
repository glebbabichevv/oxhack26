import type { HTMLAttributes, ReactNode } from "react";

// "The Ledger" primitives (DESIGN.md → Components). No dependencies beyond React + Tailwind.

export const UP = "#16a34a";
export const DOWN = "#e11d48";

/** Hairline grid: children are white cells separated by 1px seams. Pass grid-cols-* via className. */
export function Ledger({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`ledger ${className}`} {...props} />;
}

export function Cell({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`flex min-w-0 flex-col ${className}`} {...props} />;
}

export function PanelHead({ title, sub, pill }: { title: string; sub?: string; pill?: ReactNode }) {
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

/** KPI cell: label, big number, then a signed delta or a muted hint (never an empty delta). */
export function Kpi({ label, value, delta, deltaText, suffix, hint }: {
  label: string; value: string; delta?: number; deltaText?: string; suffix?: string; hint?: string;
}) {
  const color = delta === undefined || delta === 0 ? "rgba(9,9,11,0.45)" : delta > 0 ? UP : DOWN;
  return (
    <Cell className="p-5 sm:p-6">
      <p className="text-[14px] text-ink-muted">{label}</p>
      <p className="mt-3 font-display text-[34px] font-semibold leading-none tracking-tight text-ink-strong tabular-nums sm:text-[40px]">
        {value}
      </p>
      {delta === undefined ? (
        <p className="mt-3 text-[13px] text-ink-muted/70">{hint ?? ""}</p>
      ) : (
        <p className="mt-3 flex items-center gap-1.5 text-[13px]">
          {delta !== 0 ? <Arrow up={delta > 0} color={color} /> : null}
          <span style={{ color }} className="font-semibold tabular-nums">{deltaText}</span>
          {suffix ? <span className="text-ink-muted/70">{suffix}</span> : null}
        </p>
      )}
    </Cell>
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

const actionStyle = {
  BUY_YES: "bg-up-tint text-up",
  BUY_NO: "bg-down-tint text-down",
  NO_TRADE: "bg-page text-ink-muted",
} as const;
const actionLabel = { BUY_YES: "Buy YES", BUY_NO: "Buy NO", NO_TRADE: "No trade" } as const;

export function ActionPill({ action }: { action: keyof typeof actionStyle }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[13px] font-semibold ${actionStyle[action]}`}>
      {actionLabel[action]}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center rounded-full border border-seam-strong px-2.5 py-0.5 text-[12px] text-ink-muted">{children}</span>;
}

/** Bottom-anchored link inside a cell, e.g. "All markets →". */
export function PanelLink({ children, href }: { children: ReactNode; href: string }) {
  return (
    <a href={href} className="group flex items-center justify-center gap-2 border-t border-seam px-5 py-4 text-[14px] font-semibold text-ink-strong/75 transition-colors hover:bg-hover-wash hover:text-ink-strong">
      {children}
      <span className="transition-transform duration-200 group-hover:translate-x-1" aria-hidden>→</span>
    </a>
  );
}
