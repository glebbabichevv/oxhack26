/**
 * math.ts — the one place model text is prepared for remark-math + KaTeX.
 *
 * Every earlier fix here was a regex that decided about one dollar sign at a time,
 * and each one broke the case next to it: the currency escape turned the second
 * dollar of "$$7\sin\theta…$$" into "\$" because a digit followed it, the display
 * formula fell apart and the formulas after it paired with the wrong dollars. The
 * chat bubble and the task view also prepared text differently, so \[…\] rendered
 * in one and came out raw in the other.
 *
 * So the unit is the formula, not the character. One left-to-right pass finds each
 * whole span — $$…$$ (may cross lines), \[…\], \(…\), $…$ (one line) — and swaps it
 * for an opaque placeholder. Whatever runs over the prose afterwards (headings,
 * tables, paragraph merges) cannot touch a formula it cannot see. A dollar that is
 * not part of a span is money and is escaped. Code is never looked at.
 */

const OPEN = '';
const CLOSE = '';
const PLACEHOLDER = /(\d+)/g;

export interface ProtectedMath {
  /** The text with every formula replaced by a placeholder and every stray `$` escaped. */
  text: string;
  /** Put the formulas back. */
  restore(s: string): string;
}

/** Does the text contain a formula placeholder? For prose rules that must leave formulas alone. */
export const hasMathPlaceholder = (s: string): boolean => s.includes(OPEN);

/** Does the text end with a formula (trailing whitespace aside)? */
export const endsWithMathPlaceholder = (s: string): boolean => s.trimEnd().endsWith(CLOSE);

/**
 * Is `body` (what sits between two single dollars on one line) a formula?
 *
 * remark-math's own rule first: a span that opens or closes on whitespace is not
 * math to it either. Then prose tells: emphasis markers, and a Cyrillic word
 * outside \text{}. A body with LaTeX in it (a command, ^, _, braces, =) may be
 * long; a bare one has to be short, since "$5 and more words $" is two prices.
 */
function isInlineMath(body: string): boolean {
  if (!body || /^\s|\s$/.test(body)) return false;
  if (body.includes('**') || body.includes('__')) return false;
  if (/[Ѐ-ӿ]{3,}/.test(body.replace(/\\(?:text|mathrm|textbf|mbox)\{[^}]*\}/g, ''))) return false;
  const latex = /\\[a-zA-Z]+|[\^_{}=]/.test(body);
  return body.length <= (latex ? 400 : 40);
}

function scanProse(src: string, spans: string[]): string {
  const keep = (formula: string) => {
    spans.push(formula);
    return `${OPEN}${spans.length - 1}${CLOSE}`;
  };
  let out = '';
  let i = 0;
  while (i < src.length) {
    const c = src[i];

    if (c === '\\') {
      const n = src[i + 1];
      if (n === '$') { out += '\\$'; i += 2; continue; }
      if (n === '[') {
        const end = src.indexOf('\\]', i + 2);
        if (end >= 0 && src.slice(i + 2, end).trim()) { out += keep(`$$${src.slice(i + 2, end)}$$`); i = end + 2; continue; }
      }
      if (n === '(') {
        const end = src.indexOf('\\)', i + 2);
        const body = end >= 0 ? src.slice(i + 2, end) : '';
        if (body.trim() && !body.includes('\n')) { out += keep(`$${body.trim()}$`); i = end + 2; continue; }
      }
      out += c + (n ?? '');
      i += 2;
      continue;
    }

    if (c === '$' && src[i + 1] === '$') {
      const end = src.indexOf('$$', i + 2);
      if (end >= 0 && src.slice(i + 2, end).trim()) { out += keep(src.slice(i, end + 2)); i = end + 2; continue; }
      // Unclosed — mid-stream, usually. Shown as text until its closing half arrives,
      // rather than a math block that swallows the rest of the answer in red.
      out += '\\$\\$';
      i += 2;
      continue;
    }

    if (c === '$') {
      const lineEnd = src.indexOf('\n', i);
      const stop = lineEnd < 0 ? src.length : lineEnd;
      let close = -1;
      for (let j = i + 1; j < stop; j++) {
        if (src[j] === '\\') { j++; continue; }
        if (src[j] === '$') { close = j; break; }
      }
      if (close > 0 && src[close + 1] !== '$' && isInlineMath(src.slice(i + 1, close))) {
        out += keep(src.slice(i, close + 1));
        i = close + 1;
        continue;
      }
      out += '\\$';
      i += 1;
      continue;
    }

    // "(\gamma + 1)" — models sometimes wrap a formula in plain parentheses.
    if (c === '(' && src[i + 1] === '\\') {
      const m = /^\(\\[a-zA-Z]+[^()\n]*\)/.exec(src.slice(i));
      if (m && !/[Ѐ-ӿ]/.test(m[0])) { out += keep(`$${m[0].slice(1, -1)}$`); i += m[0].length; continue; }
    }

    out += c;
    i += 1;
  }
  return out;
}

export function protectMath(md: string): ProtectedMath {
  const spans: string[] = [];
  const code = /```[\s\S]*?(?:```|$)|`[^`\n]*`/g;
  let text = '';
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = code.exec(md)) !== null) {
    text += scanProse(md.slice(last, m.index), spans) + m[0];
    last = code.lastIndex;
    if (m[0].length === 0) code.lastIndex++;
  }
  text += scanProse(md.slice(last), spans);
  return {
    text,
    restore: (s) => s.replace(PLACEHOLDER, (_m, n: string) => spans[Number(n)] ?? ''),
  };
}

/** Prepare text for remark-math in one step: find formulas, escape money, put formulas back. */
export function prepareMath(md: string): string {
  const p = protectMath(md);
  return p.restore(p.text);
}
