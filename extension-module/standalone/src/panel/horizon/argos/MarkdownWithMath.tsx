/**
 * MarkdownWithMath.tsx
 *
 * Shared renderer: markdown (tables, bold, lists) + LaTeX ($...$, $$...$$, \(...\), \[...\]).
 * Uses remarkMath + rehypeKatex for proper KaTeX rendering.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { prepareMath } from './math';

interface MarkdownWithMathProps {
  content: string;
  className?: string;
}

export const MarkdownWithMath: React.FC<MarkdownWithMathProps> = ({ content, className }) => {
  if (!content) return null;
  const normalized = prepareMath(content);
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalized}
      </ReactMarkdown>
    </div>
  );
};

/** For inline/simple text with math (e.g. table cells). */
export function renderWithMath(content: string): React.ReactNode {
  if (!content) return null;
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]} rehypePlugins={[rehypeKatex]}>
      {prepareMath(content)}
    </ReactMarkdown>
  );
}
