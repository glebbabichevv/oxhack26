// Horizon tokens as a Tailwind v3 preset (only if the app uses Tailwind v3;
// on v4 use tokens.css instead). Colours read the CSS variables in tokens.css,
// so import tokens.css too. Source of truth: /DESIGN.md.
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        surface: "var(--surface)",
        card: "var(--card)",
        border: "var(--border)",
        text: { DEFAULT: "var(--text)", muted: "var(--text-muted)" },
        primary: { DEFAULT: "var(--primary)", hover: "var(--primary-hover)", soft: "var(--primary-soft)" },
        positive: { DEFAULT: "var(--positive)", soft: "var(--positive-soft)" },
        negative: { DEFAULT: "var(--negative)", soft: "var(--negative-soft)" },
        neutral: { DEFAULT: "var(--neutral)", soft: "var(--neutral-soft)" },
        warning: { DEFAULT: "var(--warning)", soft: "var(--warning-soft)" },
        info: { DEFAULT: "var(--info)", soft: "var(--info-soft)" },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        caption: ["11px", { lineHeight: "1.45", letterSpacing: "0.005em" }],
        footnote: ["12px", { lineHeight: "1.5", letterSpacing: "0" }],
        body: ["13px", { lineHeight: "1.55", letterSpacing: "-0.006em" }],
        subhead: ["15px", { lineHeight: "1.4", letterSpacing: "-0.014em" }],
        title: ["17px", { lineHeight: "1.32", letterSpacing: "-0.021em" }],
        display: ["22px", { lineHeight: "1.22", letterSpacing: "-0.028em" }],
        hero: ["28px", { lineHeight: "1.16", letterSpacing: "-0.035em" }],
      },
      borderRadius: { chip: "7px", control: "11px", card: "15px", panel: "20px", sheet: "26px" },
      boxShadow: { card: "var(--shadow-card)", raised: "var(--shadow-raised)", overlay: "var(--shadow-overlay)" },
      transitionDuration: { fast: "140ms", base: "240ms", slow: "420ms" },
      transitionTimingFunction: { soft: "cubic-bezier(0.22, 1, 0.36, 1)" },
      transitionProperty: {
        ui: "background-color, border-color, color, fill, stroke, box-shadow, transform, opacity",
      },
    },
  },
};
