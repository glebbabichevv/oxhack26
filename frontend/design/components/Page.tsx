import type { ReactNode } from "react";

// "The Quiet Page" primitives (DESIGN.md → Components). React + Tailwind only, no client hooks.

export function Nav({ links, action }: { links: { label: string; href: string }[]; action?: ReactNode }) {
  return (
    <nav className="sticky top-4 z-40 mx-auto mt-4 flex h-[52px] max-w-[1120px] items-center justify-between rounded-full border border-black/[0.04] bg-[rgba(250,250,250,0.9)] pl-4 pr-2 shadow-nav">
      <span className="text-[17px] font-medium text-ink-strong">Horizon<span className="text-ink-faint">.</span></span>
      <div className="hidden gap-7 text-ink-muted md:flex">
        {links.map((l) => <a key={l.href} href={l.href} className="transition-colors hover:text-ink-strong">{l.label}</a>)}
      </div>
      {action}
    </nav>
  );
}

/** Serif claim with a greyed second line + lead paragraph. */
export function Hero({ first, second, lead }: { first: string; second?: string; lead?: string }) {
  return (
    <header className="pt-[72px]">
      <h1 className="font-serif text-[40px] leading-[1.06] tracking-[-0.02em] text-ink md:text-[56px]">
        {first}
        {second ? <><br /><span className="text-ink-second">{second}</span></> : null}
      </h1>
      {lead ? <p className="mt-[18px] max-w-[560px] text-[17px] leading-[1.6] text-ink-muted">{lead}</p> : null}
    </header>
  );
}

/** One ruled row of numbers with hairline separators. */
export function KpiRow({ items }: { items: { label: string; value: string; note?: string; tone?: "up" | "down" }[] }) {
  return (
    <div className="mt-11 grid grid-cols-2 border-y border-hairline md:grid-cols-4">
      {items.map((k, i) => (
        <div key={k.label} className={`py-5 pr-6 ${i > 0 ? "md:border-l md:border-hairline md:pl-6" : ""} ${i % 2 === 1 ? "border-l border-hairline pl-6 md:pl-6" : ""}`}>
          <div className="text-ink-muted">{k.label}</div>
          <div className="mt-1.5 text-[30px] font-semibold leading-[1.15] tracking-[-0.02em] tabular-nums text-ink-strong">{k.value}</div>
          {k.note ? <div className={`mt-0.5 text-[13px] ${k.tone === "up" ? "font-semibold text-up" : k.tone === "down" ? "font-semibold text-down" : "text-ink-muted"}`}>{k.note}</div> : null}
        </div>
      ))}
    </div>
  );
}

/** Text column + evidence column. */
export function Section({ title, lead, controls, children }: { title: string; lead?: string; controls?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-14 grid grid-cols-1 items-start gap-10 md:grid-cols-[1fr_1.25fr]">
      <div>
        <h2 className="font-serif text-[32px] leading-[1.2] tracking-[-0.01em]">{title}</h2>
        {lead ? <p className="mt-2.5 text-[15px] leading-[1.6] text-ink-muted">{lead}</p> : null}
        {controls ? <div className="mt-5">{controls}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** White card inside a soft grey frame (the landing's product-mock look). */
export function FramedCard({ title, meta, children }: { title?: string; meta?: string; children: ReactNode }) {
  return (
    <div className="rounded-frame bg-frame p-2 shadow-frame">
      <div className="rounded-card border border-hairline-soft bg-page p-5">
        {title ? (
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <span className="text-[15px] font-semibold text-ink-strong">{title}</span>
            {meta ? <span className="text-[12px] text-ink-faint tabular-nums">{meta}</span> : null}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}

/** Pricing-style toggle: white track, Ink active pill. */
export function Segmented<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="inline-flex rounded-full border border-black/10 bg-page p-[3px]">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}
          className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors ${o.value === value ? "bg-ink-strong text-white" : "text-ink-muted hover:text-ink-strong"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

const chip = { BUY_YES: "bg-up-tint text-up", BUY_NO: "bg-down-tint text-down", NO_TRADE: "bg-fill-soft text-ink-muted" } as const;
const chipLabel = { BUY_YES: "Buy YES", BUY_NO: "Buy NO", NO_TRADE: "No trade" } as const;

export function ActionChip({ action }: { action: keyof typeof chip }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-[3px] text-[12px] font-semibold ${chip[action]}`}>{chipLabel[action]}</span>;
}

/** One live market row: question | price | model q | chip. */
export function DecisionRow({ question, meta, price, q, action }: { question: string; meta: string; price: string; q: string; action: keyof typeof chip }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3.5 border-t border-hairline-soft py-3 first:border-t-0">
      <div className="min-w-0">
        <div className="truncate font-medium">{question}</div>
        <div className="text-[12px] text-ink-faint">{meta}</div>
      </div>
      <div className="text-right tabular-nums text-ink-muted">{price}</div>
      <div className="text-right font-semibold tabular-nums">{q}</div>
      <ActionChip action={action} />
    </div>
  );
}
