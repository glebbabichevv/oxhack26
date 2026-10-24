import { sentence, type InvestEvent } from "@/lib/invest";

const tone = { up: "bg-up-tint text-up", down: "bg-down-tint text-down", muted: "bg-fill-soft text-ink-strong" };

export function BetsFeed({ events }: { events: InvestEvent[] }) {
  if (!events.length) return <p className="text-[15px] text-ink-muted">No bets yet. The first check runs within 10 minutes of starting a plan.</p>;
  return (
    <ul className="divide-y divide-hairline">
      {events.map((e) => {
        const s = sentence(e);
        return (
          <li key={e.id} className="flex items-start justify-between gap-4 py-3.5">
            <div className="min-w-0">
              <p className="text-[15px] leading-[1.5] text-ink-strong">
                {e.url ? <a className="underline-offset-2 hover:underline focus-visible:outline-2" href={e.url} target="_blank" rel="noreferrer">{s.text}</a> : s.text}
              </p>
              <time className="text-[12px] text-ink-faint tabular-nums" dateTime={e.t}>
                {new Date(e.t).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </time>
            </div>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-[13px] font-semibold tabular-nums ${tone[s.tone]}`}>{s.chip}</span>
          </li>
        );
      })}
    </ul>
  );
}
