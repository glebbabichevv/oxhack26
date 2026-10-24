/**
 * rehypeFadeWords.ts
 *
 * While an answer streams, every word becomes its own <span class="argos-w">,
 * which fades in once when it mounts. The markdown is re-rendered every frame,
 * but React keys children by tag and position, so a word already on screen
 * keeps its span and never replays the fade — only the newest words do.
 *
 * Characters were already paced evenly (useSmoothStream); what still read as
 * jerky was each one landing at full ink. The mask that dimmed the whole last
 * line could not help with that: it faded a line, not the words that were new.
 *
 * Only used while streaming. Code, formulas and SVG keep their own markup.
 */

import type { Root, Element, ElementContent } from 'hast';

const SKIP_TAGS = new Set(['pre', 'code', 'svg', 'math', 'script', 'style']);

function skip(el: Element): boolean {
  if (SKIP_TAGS.has(el.tagName)) return true;
  const cls = el.properties?.className;
  const list = Array.isArray(cls) ? cls.map(String) : typeof cls === 'string' ? [cls] : [];
  return list.some((c) => c.startsWith('katex') || c === 'argos-code');
}

function split(children: ElementContent[]): ElementContent[] {
  const out: ElementContent[] = [];
  for (const child of children) {
    if (child.type === 'text') {
      const words = child.value.match(/\s+|\S+\s*/g) ?? [];
      for (const w of words) {
        if (!w.trim()) { out.push({ type: 'text', value: w }); continue; }
        out.push({ type: 'element', tagName: 'span', properties: { className: ['argos-w'] }, children: [{ type: 'text', value: w }] });
      }
    } else {
      if (child.type === 'element' && !skip(child)) child.children = split(child.children);
      out.push(child);
    }
  }
  return out;
}

export function rehypeFadeWords() {
  return (tree: Root) => {
    tree.children = tree.children.map((c) => {
      if (c.type === 'element' && !skip(c)) c.children = split(c.children);
      return c;
    });
  };
}
