// Render public/icons/icon.svg to 16/48/128 px PNGs with Playwright (dev-time only).
import { createRequire } from 'module';
import { readFileSync } from 'fs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH ?? `${process.env.HOME}/.claude/skills/gstack/node_modules/playwright`);
const dir = new URL('../public/icons/', import.meta.url).pathname;
const svg = readFileSync(dir + 'icon.svg', 'utf8');
const b = await chromium.launch();
for (const s of [16, 48, 128]) {
  const p = await b.newPage({ viewport: { width: s, height: s } });
  await p.setContent(`<html><body style="margin:0;background:transparent">${svg.replace('<svg ', `<svg width="${s}" height="${s}" `)}</body></html>`);
  await p.screenshot({ path: `${dir}icon${s}.png`, omitBackground: true });
}
await b.close();
