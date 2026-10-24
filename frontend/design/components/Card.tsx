import type { HTMLAttributes, ReactNode } from "react";

// Horizon card, metric and action chip (DESIGN.md → Components). No dependencies.

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-card border border-border bg-card p-5 ${className}`} {...props} />;
}

export function CardHeader({ title, meta }: { title: ReactNode; meta?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h3 className="text-subhead font-semibold text-text">{title}</h3>
      {meta ? <span className="text-caption text-text-muted tabular-nums">{meta}</span> : null}
    </div>
  );
}

export function Metric({ label, value, tone }: { label: string; value: ReactNode; tone?: "positive" | "negative" }) {
  const color = tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text";
  return (
    <div>
      <div className="text-caption text-text-muted">{label}</div>
      <div className={`text-display font-semibold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

const actionStyles = {
  BUY_YES: "bg-positive-soft text-positive",
  BUY_NO: "bg-negative-soft text-negative",
  NO_TRADE: "bg-neutral-soft text-neutral",
} as const;

const actionLabels = { BUY_YES: "Buy YES", BUY_NO: "Buy NO", NO_TRADE: "No trade" } as const;

export function ActionChip({ action }: { action: keyof typeof actionStyles }) {
  return (
    <span className={`inline-flex h-[22px] items-center rounded-chip px-2 text-caption font-medium ${actionStyles[action]}`}>
      {actionLabels[action]}
    </span>
  );
}
