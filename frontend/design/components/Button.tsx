import type { ButtonHTMLAttributes } from "react";

// Horizon button (DESIGN.md → Components → Button). No dependencies.
type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-2 rounded-control font-medium transition-ui duration-fast " +
  "disabled:opacity-50 disabled:pointer-events-none";

const variants: Record<Variant, string> = {
  primary: "bg-[#0F172A] text-white hover:bg-[#1E293B] dark:bg-white dark:text-[#0F172A] dark:hover:bg-[#E4E4E7]",
  secondary: "bg-card text-text border border-border hover:bg-surface",
  ghost: "bg-transparent text-text-muted hover:bg-primary-soft hover:text-text",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-footnote",
  md: "h-9 px-3.5 text-body",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props} />;
}
