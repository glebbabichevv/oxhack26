// Copy the manifest into dist and refuse a bundle that mentions the base product's servers.
import { copyFileSync, readdirSync, readFileSync, statSync } from 'fs';
import { join } from 'path';
const root = new URL('..', import.meta.url).pathname;
const dist = join(root, 'dist');
copyFileSync(join(root, 'manifest.json'), join(dist, 'manifest.json'));
const banned = /supabase|tryargos|render\.com|api\.tryargos|localhost:3000/i;
const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]));
const bad = walk(dist).filter((f) => /\.(js|html|json|css)$/.test(f) && banned.test(readFileSync(f, 'utf8')));
if (bad.length) { console.error('Banned strings in', bad); process.exit(1); }
console.log('dist ok: no Argos server strings');
