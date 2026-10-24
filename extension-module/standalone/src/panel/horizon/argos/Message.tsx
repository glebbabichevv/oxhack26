/**
 * Argos's message rendering, ported for Horizon's agent turns: the user's command as Argos's user
 * bubble, the agent's text as an Argos assistant message (markdown + LaTeX via KaTeX, the same
 * prose ladder, words settling in once via rehypeFadeWords). Source:
 * extension/src/panel/components/MessageBubble.tsx (assistant + user branches).
 */
import { Component, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { prepareMath } from './math';
import { rehypeFadeWords } from './rehypeFadeWords';

const REHYPE_FRESH = [rehypeKatex, rehypeFadeWords];
const REHYPE_SETTLED = [rehypeKatex];

/** If markdown ever throws, show the text as is rather than nothing. */
class MarkdownErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

const PROSE = `prose prose-sm max-w-none
  prose-headings:text-[#0f172a] prose-headings:font-semibold
  prose-p:text-[#0f172a] prose-p:leading-relaxed prose-p:text-body prose-p:my-1.5
  prose-strong:text-[#0f172a] prose-em:text-[#0f172a]
  prose-a:text-[#0f172a] prose-a:underline prose-a:decoration-black/20 prose-a:underline-offset-2
  prose-ul:text-[#0f172a] prose-ol:text-[#0f172a] prose-li:text-[#0f172a] prose-li:text-body prose-li:my-0.5
  prose-blockquote:text-[#0f172a]/60 prose-blockquote:not-italic
  prose-table:border-collapse prose-table:w-full
  prose-th:border prose-th:border-gray-200 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:bg-gray-50 prose-th:text-footnote
  prose-td:border prose-td:border-gray-200 prose-td:px-3 prose-td:py-2 prose-td:text-footnote`;

export function AssistantMessage({ text, fresh = false, children }: { text?: string; fresh?: boolean; children?: ReactNode }) {
  return (
    <div className="group flex w-full items-start justify-start">
      <div className="ai-message-content min-w-0 flex-1 space-y-1.5">
        {text ? (
          <div className={PROSE}>
            <MarkdownErrorBoundary fallback={<div style={{ whiteSpace: 'pre-wrap' }}>{text}</div>}>
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]} rehypePlugins={(fresh ? REHYPE_FRESH : REHYPE_SETTLED) as never}>
                {prepareMath(text)}
              </ReactMarkdown>
            </MarkdownErrorBoundary>
          </div>
        ) : null}
        {children}
      </div>
    </div>
  );
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex w-full justify-end">
      <div className="hz-bubble-user relative max-w-[85%] overflow-hidden rounded-panel rounded-br-chip px-3.5 py-2.5 text-body leading-relaxed text-[#0f172a]" style={{ wordWrap: 'break-word' }}>
        <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>{text}</div>
      </div>
    </div>
  );
}

/** Markdown + LaTeX for static copy (Details). */
export function Md({ text, className }: { text: string; className?: string }) {
  return (
    <div className={`ai-message-content ${className ?? ''}`}>
      <div className={PROSE}>
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]} rehypePlugins={REHYPE_SETTLED as never}>{prepareMath(text)}</ReactMarkdown>
      </div>
    </div>
  );
}
