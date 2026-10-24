import type { ButtonHTMLAttributes } from "react";

// Pill buttons (DESIGN.md → Components → Buttons). The CTA needs tokens.css (.hz-cta-*).
type Variant = "primary" | "quiet";

export function Button({ variant = "primary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const look = variant === "primary" ? "bg-ink-strong text-white hover:bg-[#2a2a2e]" : "bg-fill-soft text-ink-strong hover:bg-black/[0.08]";
  return (
    <button
      className={`inline-flex h-9 items-center justify-center gap-2 rounded-full px-4 text-[14px] font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 ${look} ${className}`}
      {...props}
    />
  );
}

/** The one big call to action: dark pill sitting on a soft blurred grounding shadow. */
export function CtaButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <span className="hz-cta-wrap">
      <span aria-hidden className="hz-cta-shadow" />
      <button className="hz-cta group inline-flex h-[52px] items-center gap-2 rounded-full px-[30px] text-[16px] font-medium" {...props}>
        {children}
        <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
      </button>
    </span>
  );
}
