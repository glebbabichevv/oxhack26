import type { ButtonHTMLAttributes } from "react";

// Pill buttons (DESIGN.md → Components → Buttons). Needs tokens.css for .hz-glass-bar / .hz-cta.
type Variant = "primary" | "cta" | "glass";

const variants: Record<Variant, string> = {
  primary: "h-9 px-4 bg-ink-strong text-white hover:bg-graphite",
  cta: "hz-cta h-[54px] px-8 text-[17px] hover:brightness-110",
  glass: "hz-glass-bar h-9 px-4 text-ink-strong hover:bg-white/80",
};

export function Button({ variant = "glass", className = "", children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`group inline-flex items-center justify-center gap-2 rounded-full text-[14px] font-semibold transition-all duration-150 disabled:pointer-events-none disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
      {variant === "cta" ? <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span> : null}
    </button>
  );
}
