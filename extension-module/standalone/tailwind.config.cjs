/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./panel.html', './src/panel/**/*.{ts,tsx}'],
  theme: { extend: { borderRadius: { chip: '7px', control: '11px', card: '15px' } } },
  plugins: [],
};
