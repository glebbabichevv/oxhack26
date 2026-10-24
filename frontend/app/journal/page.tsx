"use client";

import { useEffect, useState } from "react";
import { ActionChip, FramedCard, Hero, Nav, Section, Segmented } from "@/design/components/Page";
import { CachedNote } from "@/components/CachedNote";
import { API_URL, cents, getJSON, int, pct } from "@/lib/api";
import type { CapsuleData } from "@/components/Capsule";
import { TrackChart, type Track } from "@/components/TrackChart";

// Decision Journal (GET /api/journal): every call someone acted on, what Horizon said then, and how it ended.
type Entry = {
  id: string; ts: string; market_id: string; slug?: string | null; question: string;
  side: "YES" | "NO" | null; price: number; q?: number | null; q_low?: number | null; q_high?: number | null;
  action: "BUY_YES" | "BUY_NO" | "NO_TRADE"; stake_usd?: number | null; source?: string | null; status?: string | null;
  outcome: 0 | 1 | null; result_per_dollar: number | null; right: boolean | null;
};
type Journal = {
  storage: string; n_total: number; n_shown: number; records: Entry[];
  summary: { n_trades: number; n_resolved: number; n_right: number; mean_result_per_dollar: number | null };
};

const REFRESH_MS = 60_000;
const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
const perDollar = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(0)}¢`;

function Result({ e }: { e: Entry }) {
  if (e.action === "NO_TRADE") return <span className="text-[13px] text-ink-faint">no stake</span>;
  if (e.result_per_dollar == null) return <span className="text-[13px] text-ink-muted">open</span>;
  return (
    <span className={`text-[13px] font-semibold tabular-nums ${e.right ? "text-up" : "text-down"}`}>
      {e.right ? "won" : "lost"} {perDollar(e.result_per_dollar)}<span className="font-normal text-ink-faint"> per $1</span>
    </span>
  );
}

function Row({ e }: { e: Entry }) {
  // Horizon's probability for the side taken (q is always P(YES)).
  const horizon = e.q == null ? null : e.side === "NO" ? 1 - e.q : e.q;
  const paid = e.side ? `${cents(e.price)} for ${e.side}` : `market ${cents(e.price)}`;
  const meta = [when(e.ts), e.source, e.status, e.stake_usd ? `$${e.stake_usd.toFixed(0)}` : null].filter(Boolean).join(" · ");
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3.5 gap-y-1 border-t border-hairline-soft py-3 first:border-t-0 md:grid-cols-[1fr_auto_auto_auto]">
      <div className="col-span-2 min-w-0 md:col-span-1">
        {e.slug ? (
          <a href={`https://polymarket.com/event/${e.slug}`} target="_blank" rel="noreferrer" className="line-clamp-2 font-medium hover:underline hover:decoration-ink-faint hover:underline-offset-4 md:line-clamp-1">{e.question}</a>
        ) : <div className="line-clamp-2 font-medium md:line-clamp-1">{e.question}</div>}
        <div className="text-[12px] text-ink-faint tabular-nums">{meta}</div>
      </div>
      <div className="text-[13px] tabular-nums text-ink-muted md:text-right">
        {paid}{horizon != null ? <> · Horizon <b className="font-semibold text-ink-strong">{pct(horizon)}</b></> : null}
      </div>
      <ActionChip action={e.action} />
      <div className="text-right md:w-[132px]"><Result e={e} /></div>
    </div>
  );
}

export default function JournalPage() {
  const [me, setMe] = useState<string>();
  const [scope, setScope] = useState<"all" | "me">("all");
  const [data, setData] = useState<Journal>();
  const [capsule, setCapsule] = useState<CapsuleData>();
  const [track, setTrack] = useState<Track>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("me");
    if (id) { setMe(id); setScope("me"); }
    getJSON<CapsuleData>("/api/capsule").then(setCapsule).catch(() => undefined);
    const loadTrack = () => getJSON<Track>("/api/track").then(setTrack).catch(() => undefined);
    loadTrack();
    const t = setInterval(() => { if (document.visibilityState === "visible") loadTrack(); }, 5 * 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    // A failed refresh keeps the last good data; one quick retry rides out an API restart.
    const get = () => getJSON<Journal>(`/api/journal?limit=100${scope === "me" && me ? `&me=${encodeURIComponent(me)}` : ""}`);
    const load = () =>
      get()
        .catch(() => new Promise<Journal>((ok) => setTimeout(ok, 3000)).then(get))
        .then((d) => { setData(d); setError(undefined); })
        .catch((e) => setData((prev) => { if (!prev) setError(String(e)); return prev; }));
    load();
    const t = setInterval(() => { if (document.visibilityState === "visible") load(); }, REFRESH_MS);
    return () => clearInterval(t);
  }, [scope, me]);

  const s = data?.summary;
  return (
    <>
      <Nav links={[{ label: "Evidence", href: "/" }, { label: "Decisions", href: "#decisions" }, { label: "My results", href: me ? `/me?id=${encodeURIComponent(me)}` : "/me" }, { label: "Seals", href: "#seals" }]} />
      <main className="mx-auto max-w-[1120px] px-4 pb-24">
        <CachedNote paths={["/api/journal", "/api/track", "/api/capsule"]} className="mt-4" />
        {error ? (
          <div className="mt-6 rounded-input bg-down-tint px-4 py-3 text-[13px] text-down">Can&apos;t load the journal from {API_URL} ({error}).</div>
        ) : null}
        <Hero
          first="Every call, kept."
          second="Then scored when the market resolves."
          lead="The Horizon extension logs each decision with what the model said at that moment: the price, Horizon's probability and the action, including the times it said not to trade. Nothing is edited afterwards; outcomes come from Polymarket's own resolution."
        />

        <div id="track">
          <Section
            title="Cumulative result per $1"
            lead="Every resolved decision counts as $1 on the side taken, in the order the markets resolved: the journal's logged calls, and every buy call in Seal 1."
            controls={<p className="text-[12px] text-ink-faint">Live: markets resolve overnight; nothing here is backtest.</p>}
          >
            <FramedCard>{track ? <TrackChart track={track} /> : <div className="h-[200px] animate-pulse rounded-input bg-fill-soft" />}</FramedCard>
          </Section>
        </div>

        <div id="decisions">
          <Section
            title={s && s.n_resolved ? `${s.n_right} of ${s.n_resolved} resolved trades won` : "Decisions"}
            lead={s && s.mean_result_per_dollar != null
              ? `Average result ${perDollar(s.mean_result_per_dollar)} per $1 staked, before fees, over the resolved trades shown. A handful of trades says little; the out-of-time backtest on the evidence page is the larger test.`
              : "Trades show their result per $1 staked once the market resolves; open ones say so."}
            controls={
              <div className="flex flex-col items-start gap-3">
                {me ? (
                  <>
                    <Segmented label="Whose decisions" options={[{ value: "all", label: "Everyone" }, { value: "me", label: "Mine" }]} value={scope} onChange={setScope} />
                    <a href={`/me?id=${encodeURIComponent(me)}`} className="text-[13px] font-medium text-ink-strong underline decoration-hairline underline-offset-4 hover:decoration-ink-faint">My results: am I up or down?</a>
                  </>
                ) : (
                  <p className="text-[12px] text-ink-faint">Open this page from the extension to see your own decisions (?me=…).</p>
                )}
                {data ? <p className="text-[12px] text-ink-faint tabular-nums">{int(data.n_total)} decisions{s ? ` · ${int(s.n_trades)} trades in view` : ""} · refreshes every minute</p> : null}
              </div>
            }
          >
            <FramedCard>
              {!data ? (
                <div className="h-[240px] animate-pulse rounded-input bg-fill-soft" />
              ) : data.records.length ? (
                data.records.map((e) => <Row key={e.id} e={e} />)
              ) : (
                <p className="py-10 text-center text-ink-muted">{scope === "me" ? "No decisions from this install yet." : "No decisions logged yet."}</p>
              )}
            </FramedCard>
          </Section>
        </div>

        {capsule?.seals.length ? (
          <div id="seals">
            <Section
              title="Sealed predictions"
              lead="Before the outcomes existed we hashed Horizon's probabilities for every market ending before judging. The hash is public; the file opens after the markets resolve."
            >
              <div className="min-w-0">
                {capsule.seals.map((seal, i) => (
                  <div key={seal.sha256} className="border-t border-ink-strong pt-3 pb-6">
                    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
                      <span className="text-[15px] font-semibold text-ink-strong">Seal {i + 1}, {when(seal.sealed_at)} London</span>
                      <span className="text-[12px] text-ink-faint tabular-nums">{int(seal.n_markets)} markets · {seal.opened ? `opened ${when(seal.opened.opened_at)}` : `opens before ${when(seal.deadline)}`}</span>
                    </div>
                    <dl className="grid grid-cols-[96px_1fr] gap-x-4 gap-y-1.5 text-[13px]">
                      <dt className="text-ink-muted">SHA-256</dt>
                      <dd className="min-w-0 break-all font-mono text-[12px] text-ink-strong">{seal.sha256}</dd>
                      <dt className="text-ink-muted">Timestamp</dt>
                      <dd className="text-ink-strong">{seal.timestamped ? "OpenTimestamps (Bitcoin calendars)" : "git commit"}</dd>
                      <dt className="text-ink-muted">File</dt>
                      <dd className="min-w-0 break-all text-ink-strong"><a className="underline decoration-hairline underline-offset-4 hover:decoration-ink-faint" href={`https://github.com/glebbabichevv/oxhack26/blob/main/capsule/${seal.name}`} target="_blank" rel="noreferrer">capsule/{seal.name}</a></dd>
                    </dl>
                  </div>
                ))}
                <p className="text-[12px] text-ink-faint">Scoring rules: <a className="underline decoration-hairline underline-offset-4" href="https://github.com/glebbabichevv/oxhack26/blob/main/capsule/EXPECTATIONS.md" target="_blank" rel="noreferrer">capsule/EXPECTATIONS.md</a>, committed before the first seal.</p>
              </div>
            </Section>
          </div>
        ) : null}

        <footer className="mt-20 border-t border-hairline pt-6 text-[12px] text-ink-faint">
          Results per $1 are before Polymarket&apos;s taker fee. Install ids are random per extension install; nothing else about you is stored. Not investment advice.
        </footer>
      </main>
    </>
  );
}
