// Horizon tokens as a Tailwind v3 preset (only if the app uses Tailwind v3; on v4 use tokens.css).
// Import tokens.css too: colours read its CSS variables. Source of truth: /DESIGN.md.
/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        cell: "var(--cell)",
        seam: { DEFAULT: "var(--seam)", strong: "var(--seam-strong)" },
        ink: { DEFAULT: "var(--ink)", strong: "var(--ink-strong)", muted: "var(--ink-muted)", faint: "var(--ink-faint)" },
        graphite: "var(--graphite)",
        ash: "var(--ash)",
        up: { DEFAULT: "var(--up)", tint: "var(--up-tint)" },
        down: { DEFAULT: "var(--down)", tint: "var(--down-tint)" },
        "hover-wash": "var(--hover-wash)",
      },
      fontFamily: {
        sans: ["var(--font-jakarta)", "system-ui", "sans-serif"],
        display: ["var(--font-poppins)", "system-ui", "sans-serif"],
        wordmark: ["var(--font-playfair)", "Georgia", "serif"],
      },
      borderRadius: { bar: "2px", tooltip: "12px" },
      boxShadow: {
        menu: "0 8px 32px rgba(15,23,42,0.10)",
        tooltip: "inset 0 1px 0 rgba(255,255,255,0.85), 0 8px 28px rgba(0,0,0,0.10)",
      },
    },
  },
};
