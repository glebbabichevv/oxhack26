import type { KeyboardEvent, ReactNode } from "react";
import { Rail } from "@/components/Rail";

// "The Quiet Page" primitives (DESIGN.md → Components). React + Tailwind; the only client piece is Rail.

export function Nav({ links, action }: { links: { label: string; href: string }[]; action?: ReactNode }) {
  return (
    <nav className="sticky top-4 z-40 mx-auto mt-4 flex w-[calc(100%-32px)] h-[52px] max-w-[1120px] items-center justify-between rounded-full border border-black/[0.04] bg-[rgba(250,250,250,0.9)] pl-4 pr-2 shadow-nav">
      <span className="text-[17px] font-medium text-ink-strong">Horizon<span className="text-ink-faint">.</span></span>
      <div className="flex gap-3.5 pr-2 text-[13px] text-ink-muted sm:gap-7 sm:text-[14px] md:pr-0">
        {links.map((l) => <a key={l.href} href={l.href} className="-my-2 rounded-full py-3 transition-colors hover:text-ink-strong">{l.label}</a>)}
      </div>
      {action ? <span className="hidden md:inline-flex">{action}</span> : null}
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
export function KpiRow({ items }: { items: { label: string; value: ReactNode; note?: string; tone?: "up" | "down" }[] }) {
  return (
    <div className="mt-11 grid grid-cols-2 border-y border-hairline md:grid-cols-4">
      {items.map((k, i) => (
        <div key={k.label} className={`py-5 pr-6 ${i > 0 ? "md:border-l md:border-hairline md:pl-6" : ""} ${i % 2 === 1 ? "border-l border-hairline pl-6 md:pl-6" : ""}`}>
          <div className="text-ink-muted">{k.label}</div>
          <div className="mt-1.5 text-[26px] font-semibold leading-[1.15] tracking-[-0.025em] tabular-nums text-ink-strong md:text-[34px]">{k.value}</div>
          {k.note ? <div className={`mt-0.5 text-[13px] ${k.tone === "up" ? "font-semibold text-up" : k.tone === "down" ? "font-semibold text-down" : "text-ink-muted"}`}>{k.note}</div> : null}
        </div>
      ))}
    </div>
  );
}

/** Text column + evidence column. */
export function Section({ title, lead, controls, children }: { title: string; lead?: string; controls?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-20 grid grid-cols-1 items-start gap-10 md:grid-cols-[1fr_1.25fr] md:gap-16">
      <div className="relative md:sticky md:top-[104px] md:pl-7">
        <Rail />
        <h2 className="font-serif text-[32px] leading-[1.2] tracking-[-0.01em]">{title}</h2>
        {lead ? <p className="mt-2.5 text-[15px] leading-[1.6] text-ink-muted">{lead}</p> : null}
        {controls ? <div className="mt-5">{controls}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** An editorial figure: an Ink rule on top, title and meta on one line, the evidence below. No box, no shadow. */
export function FramedCard({ title, meta, children }: { title?: string; meta?: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="border-t border-ink-strong pt-3">
        {title ? (
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <span className="text-[15px] font-semibold text-ink-strong">{title}</span>
            {meta ? <span className="text-[12px] text-ink-faint tabular-nums">{meta}</span> : null}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}

/** Pricing-style toggle: white track, Ink active pill. A radio group: Tab enters at the selection, arrows move it. */
export function Segmented<T extends string>({ label, options, value, onChange }: { label: string; options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  const move = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const i = (options.findIndex((o) => o.value === value) + step + options.length) % options.length;
    onChange(options[i].value);
    (e.currentTarget.children[i] as HTMLElement | undefined)?.focus();
  };
  return (
    <div className="flex flex-col items-start gap-1.5">
      <span className="text-[12px] text-ink-faint">{label}</span>
      <div role="radiogroup" aria-label={label} onKeyDown={move} className="inline-flex rounded-full border border-black/10 bg-page p-[3px]">
        {options.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={o.value === value} tabIndex={o.value === value ? 0 : -1} onClick={() => onChange(o.value)}
            className={`min-h-8 rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-150 ${o.value === value ? "bg-ink-strong text-white" : "text-ink-muted hover:text-ink-strong"}`}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

const chip = { BUY_YES: "bg-up-tint text-up", BUY_NO: "bg-down-tint text-down", NO_TRADE: "bg-fill-soft text-ink-muted" } as const;
const chipLabel = { BUY_YES: "Buy YES", BUY_NO: "Buy NO", NO_TRADE: "No trade" } as const;

export function ActionChip({ action }: { action: keyof typeof chip }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-[3px] text-[12px] font-semibold ${chip[action]}`}>{chipLabel[action]}</span>;
}

/** Price → model on a 0–100% track: Ash tick at the price, Ink dot at the model, the model's interval as a band, the gap in the action's hue. */
export function EdgeTrack({ price, q, lo, hi, action }: { price: number; q: number; lo?: number; hi?: number; action: keyof typeof chip }) {
  const x = (v: number) => `${Math.min(Math.max(v, 0), 1) * 100}%`;
  const gap = action === "BUY_YES" ? "bg-up" : action === "BUY_NO" ? "bg-down" : "bg-ink-faint/40";
  return (
    <div className="relative h-4 w-[120px]" aria-hidden>
      <div className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
      {lo !== undefined && hi !== undefined ? <div className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-ink-strong/[0.07]" style={{ left: x(lo), right: `calc(100% - ${x(hi)})` }} /> : null}
      <div className={`absolute top-1/2 h-1 -translate-y-1/2 rounded-full ${gap}`} style={{ left: x(Math.min(price, q)), right: `calc(100% - ${x(Math.max(price, q))})` }} />
      <div className="absolute top-1/2 h-3 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#a1a1aa]" style={{ left: x(price) }} />
      <div className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-white bg-ink-strong shadow-[0_0_0_1px_rgba(17,17,19,0.15)]" style={{ left: x(q) }} />
    </div>
  );
}

/** One live market row: question | price | edge track | model q | chip. */
export function DecisionRow({ question, meta, price, q, action, href, title, track }: { question: string; meta: string; price: string; q: string; action: keyof typeof chip; href?: string; title?: string; track?: ReactNode }) {
  return (
    <div title={title} className={`grid grid-cols-[1fr_auto_auto] items-center gap-x-3.5 gap-y-1.5 border-t border-hairline-soft py-3 transition-colors duration-150 first:border-t-0 hover:bg-black/[0.015] ${track ? "md:grid-cols-[1fr_auto_auto_auto_auto]" : "md:grid-cols-[1fr_auto_auto_auto]"}`}>
      <div className="col-span-3 min-w-0 md:col-span-1">
        {href ? (
          <a href={href} target="_blank" rel="noreferrer" className="line-clamp-2 rounded-[4px] font-medium hover:underline hover:decoration-ink-faint hover:underline-offset-4 md:line-clamp-1">{question}</a>
        ) : (
          <div className="line-clamp-2 font-medium md:line-clamp-1">{question}</div>
        )}
        <div className="text-[12px] text-ink-faint">{meta}</div>
      </div>
      <div className="tabular-nums text-ink-muted md:text-right"><span className="text-ink-faint md:hidden">market </span>{price}</div>
      {track ? <div className="hidden md:block">{track}</div> : null}
      <div className="text-right font-semibold tabular-nums"><span className="font-normal text-ink-faint md:hidden">model </span>{q}</div>
      <ActionChip action={action} />
    </div>
  );
}
