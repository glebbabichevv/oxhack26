/** @type {import('tailwindcss').Config} */
// Tokens from the Argos panel (same family): type scale, radii, three durations, the house curve.
module.exports = {
  content: ['./panel.html', './src/panel/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontSize: {
        caption: ['11px', { lineHeight: '1.45', letterSpacing: '0.005em' }],
        footnote: ['12px', { lineHeight: '1.5', letterSpacing: '0' }],
        body: ['13px', { lineHeight: '1.55', letterSpacing: '-0.006em' }],
        subhead: ['15px', { lineHeight: '1.4', letterSpacing: '-0.014em' }],
        title: ['17px', { lineHeight: '1.32', letterSpacing: '-0.021em' }],
        display: ['22px', { lineHeight: '1.22', letterSpacing: '-0.028em' }],
        hero: ['28px', { lineHeight: '1.16', letterSpacing: '-0.035em' }],
      },
      borderRadius: { chip: '7px', control: '11px', card: '15px', panel: '20px', sheet: '26px' },
      transitionDuration: { fast: '140ms', base: '240ms', slow: '420ms' },
      transitionProperty: { ui: 'background-color, border-color, color, fill, stroke, box-shadow, transform, opacity, filter, backdrop-filter' },
      transitionTimingFunction: { soft: 'cubic-bezier(0.22, 1, 0.36, 1)' },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
