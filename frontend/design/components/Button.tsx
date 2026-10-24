import type { ButtonHTMLAttributes } from "react";

// Pill buttons (DESIGN.md → Components → Buttons). No dependencies.
type Variant = "primary" | "outline";

const variants: Record<Variant, string> = {
  primary: "h-11 px-5 bg-ink-strong text-white hover:bg-graphite",
  outline: "h-10 px-[18px] bg-cell text-ink-strong border border-seam-strong hover:bg-hover-wash",
};

export function Button({ variant = "outline", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-full text-[14px] font-semibold transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    />
  );
}
