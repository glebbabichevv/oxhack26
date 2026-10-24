"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ActionChip, FramedCard, KpiRow, Nav, Section } from "@/design/components/Page";
import { ASH, INK, SEAM, axisTick, gridProps, tooltipProps, xAxisProps } from "@/design/components/chartTheme";
import { API_URL, cents, getJSON, int, pct } from "@/lib/api";

// My results (GET /api/me): am I making or losing money with Horizon?
type Bet = { market_id: string; slug?: string | null; question?: string; side: "YES" | "NO"; price: number; q?: number | null;
  stake_usd: number; status: string; result: "open" | "won" | "lost"; pnl_usd: number | null; ts?: string; closed_at?: string | null };
type Book = { n: number; n_open: number; n_resolved: number; n_won: number; hit_rate: number | null; staked_usd: number;
  pnl_usd: number; per_dollar: number | null; curve: { t: string; cum_usd: number }[]; bets: Bet[] };
type Totals = { n_open: number; n_closed: number; value_usd: number; unrealized_usd: number; realized_usd: number; total_usd: number };
type Position = { title?: string; slug?: string; outcome?: string; side?: string | null; avg_price?: number; cur_price?: number; tag: "followed" | "own";
  open: boolean; realized_usd: number; unrealized_usd?: number; value_usd?: number; initial_usd?: number };
type Me = {
  journal: null | { counts: Record<string, number>; placed: Book; if_followed_all: Book; skipped: Book; note: string };
  wallet: null | { totals: Totals; followed: Totals; own: Totals; truncated: boolean; positions: Position[]; note: string };
  wallet_error: string | null;
};

const usd = (v: number) => `${v >= 0 ? "+" : "−"}$${Math.abs(v).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const perDollar = (x: number | null) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(1)}¢`);
const when = (t: number) => new Date(t).toLocaleString("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
const STATUS: Record<string, string> = { placed: "Placed", set_up: "Set up", skipped: "Skipped", shown: "Shown" };

function Curve({ mine, all }: { mine: Book; all: Book }) {
  const data = [...mine.curve.map((p) => ({ x: Date.parse(p.t), mine: p.cum_usd })), ...all.curve.map((p) => ({ x: Date.parse(p.t), all: p.cum_usd }))]
    .sort((a, b) => a.x - b.x);
  if (!data.length) return <p className="py-8 text-center text-ink-muted">No resolved bets yet. Markets resolve overnight; check back after they close.</p>;
  return (
    <div>
      <div className="h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -6 }}>
            <CartesianGrid {...gridProps} />
            <XAxis {...xAxisProps} dataKey="x" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={when} minTickGap={48} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => usd(v)} width={64} />
            <ReferenceLine y={0} stroke={SEAM} />
            <Tooltip {...tooltipProps} labelFormatter={(x: number) => when(x)} formatter={(v: number, n: string) => [usd(v), n === "mine" ? "your placed bets" : "if you'd followed Horizon"]} />
            <Line dataKey="mine" stroke={INK} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="all" stroke={ASH} strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-5 text-[12px] text-ink-muted">
        <span><span className="mr-1.5 inline-block h-[2px] w-3 align-middle" style={{ background: INK }} />your placed bets</span>
        <span><span className="mr-1.5 inline-block h-[2px] w-3 align-middle" style={{ background: ASH }} />if you&apos;d followed every Horizon pick</span>
      </div>
    </div>
  );
}

function Result({ b }: { b: Bet }) {
  if (b.result === "open" || b.pnl_usd == null) return <span className="text-[13px] text-ink-muted">open</span>;
  return <span className={`text-[13px] font-semibold tabular-nums ${b.pnl_usd > 0 ? "text-up" : "text-down"}`}>{b.result} {usd(b.pnl_usd)}</span>;
}

function BetRow({ b }: { b: Bet }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3.5 gap-y-1 border-t border-hairline-soft py-3 first:border-t-0 md:grid-cols-[1fr_auto_auto_auto]">
      <div className="col-span-2 min-w-0 md:col-span-1">
        {b.slug ? <a href={`https://polymarket.com/event/${b.slug}`} target="_blank" rel="noreferrer" className="line-clamp-2 font-medium hover:underline hover:decoration-ink-faint hover:underline-offset-4 md:line-clamp-1">{b.question}</a>
          : <div className="line-clamp-2 font-medium md:line-clamp-1">{b.question}</div>}
        <div className="text-[12px] text-ink-faint tabular-nums">{STATUS[b.status] ?? b.status} · ${b.stake_usd.toFixed(2)}{b.ts ? ` · ${when(Date.parse(b.ts))}` : ""}</div>
      </div>
      <div className="text-[13px] tabular-nums text-ink-muted md:text-right">{cents(b.price)} for {b.side}{b.q != null ? <> · Horizon <b className="font-semibold text-ink-strong">{pct(b.side === "NO" ? 1 - b.q : b.q)}</b></> : null}</div>
      <span title="Horizon pick"><ActionChip action={b.side === "NO" ? "BUY_NO" : "BUY_YES"} /></span>
      <div className="text-right md:w-[120px]"><Result b={b} /></div>
    </div>
  );
}

function WalletTotals({ label, t }: { label: string; t: Totals }) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-3 border-t border-hairline-soft py-2 text-[13px] tabular-nums first:border-t-0">
      <span className="text-ink-muted">{label} <span className="text-ink-faint">{int(t.n_open)} open · {int(t.n_closed)} closed</span></span>
      <span><b className={`font-semibold ${t.total_usd >= 0 ? "text-up" : "text-down"}`}>{usd(t.total_usd)}</b>
        <span className="ml-2 text-ink-faint">realised {usd(t.realized_usd)} · unrealised {usd(t.unrealized_usd)}</span></span>
    </div>
  );
}

export default function MePage() {
  const [id, setId] = useState<string>();
  const [wallet, setWallet] = useState<string>("");
  const [draft, setDraft] = useState("");
  const [data, setData] = useState<Me>();
  const [error, setError] = useState<string>();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setId(q.get("id") ?? q.get("me") ?? undefined);
    setWallet(q.get("wallet") ?? "");
    setDraft(q.get("wallet") ?? "");
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready || (!id && !wallet)) return;
    const qs = new URLSearchParams({ ...(id ? { install_id: id } : {}), ...(wallet ? { wallet } : {}) });
    getJSON<Me>(`/api/me?${qs}`).then((d) => { setData(d); setError(undefined); }).catch((e) => setError(String(e)));
  }, [ready, id, wallet]);

  const submitWallet = (e: React.FormEvent) => {
    e.preventDefault();
    const w = draft.trim();
    if (w && !/^0x[0-9a-fA-F]{40}$/.test(w)) { setError("A wallet is a public address: 0x followed by 40 hex characters."); return; }
    const q = new URLSearchParams(window.location.search);
    if (w) q.set("wallet", w); else q.delete("wallet");
    window.history.replaceState(null, "", `${window.location.pathname}?${q}`);
    setWallet(w);
  };

  const j = data?.journal;
  const placed = j?.placed;
  const headline = !placed || !placed.n_resolved ? "No resolved bets yet." : placed.pnl_usd >= 0 ? `You're up ${usd(placed.pnl_usd).slice(1)}.` : `You're down ${usd(placed.pnl_usd).slice(1)}.`;

  return (
    <>
      <Nav links={[{ label: "Evidence", href: "/" }, { label: "Journal", href: id ? `/journal?me=${encodeURIComponent(id)}` : "/journal" }, { label: "My bets", href: "#bets" }, { label: "Wallet", href: "#wallet" }]} />
      <main className="mx-auto max-w-[1120px] px-4 pb-24">
        {error ? <div className="mt-6 rounded-input bg-down-tint px-4 py-3 text-[13px] text-down">{error.startsWith("A wallet") ? error : `Can't load your results from ${API_URL} (${error}).`}</div> : null}
        <header className="pt-[72px]">
          <h1 className="font-serif text-[40px] leading-[1.06] tracking-[-0.02em] text-ink md:text-[56px]">{ready && !id && !wallet ? "My results." : headline}</h1>
          <p className="mt-[18px] max-w-[620px] text-[17px] leading-[1.6] text-ink-muted">
            {!id && ready ? "Open this page from the Horizon extension (My results) so it knows your install, or add a public wallet address below."
              : placed && placed.n_resolved
                ? `${perDollar(placed.per_dollar)} per $1 after fees · ${pct(placed.hit_rate ?? 0)} of ${int(placed.n_resolved)} resolved bets won · ${int(placed.n_open)} still open. Placed bets are self-reported in the extension.`
                : placed ? `${int(placed.n)} placed bets, all still open. Markets resolve overnight. Placed bets are self-reported in the extension.` : ""}
          </p>
        </header>

        {j ? (
          <>
            <KpiRow items={[
              { label: "Your placed bets", value: placed!.n_resolved ? usd(placed!.pnl_usd) : "–", note: `${int(placed!.n)} bets · ${perDollar(placed!.per_dollar)} per $1`, tone: placed!.n_resolved ? (placed!.pnl_usd >= 0 ? "up" : "down") : undefined },
              { label: "If you'd followed every pick", value: j.if_followed_all.n_resolved ? usd(j.if_followed_all.pnl_usd) : "–", note: `${int(j.if_followed_all.n)} picks · ${perDollar(j.if_followed_all.per_dollar)} per $1`, tone: j.if_followed_all.n_resolved ? (j.if_followed_all.pnl_usd >= 0 ? "up" : "down") : undefined },
              { label: "Picks you skipped", value: j.skipped.n_resolved ? usd(j.skipped.pnl_usd) : "–", note: `${int(j.skipped.n)} skipped · ${int(j.skipped.n_resolved)} resolved` },
              { label: "Decisions", value: int(Object.values(j.counts).reduce((a, b) => a + b, 0)), note: `${int(j.counts.shown ?? 0)} shown · ${int(j.counts.set_up ?? 0)} set up · ${int(j.counts.placed ?? 0)} placed · ${int(j.counts.skipped ?? 0)} skipped` },
            ]} />
            <Section title="Your bets vs following Horizon" lead="Cumulative P&L in dollars by the time each market resolved, after Polymarket's taker fee, at the price you logged.">
              <FramedCard><Curve mine={placed!} all={j.if_followed_all} /></FramedCard>
            </Section>
            <div id="bets">
              <Section title="Every Horizon pick you saw" lead={j.note}>
                <FramedCard>
                  {j.if_followed_all.bets.length ? j.if_followed_all.bets.map((b) => <BetRow key={`${b.market_id}-${b.side}`} b={b} />)
                    : <p className="py-10 text-center text-ink-muted">No Horizon picks logged from this install yet.</p>}
                </FramedCard>
              </Section>
            </div>
          </>
        ) : null}

        <div id="wallet">
          <Section
            title="Real Polymarket positions"
            lead="Add your public wallet address to see what actually happened on-chain, split into positions that match a Horizon pick you set up or placed and your own. Read only: we never ask for keys, and the address stays in this page's URL, not on our server."
            controls={
              <form onSubmit={submitWallet} className="flex w-full max-w-[420px] gap-2">
                <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="0x… public address" aria-label="Public wallet address" spellCheck={false}
                  className="h-9 min-w-0 flex-1 rounded-full border border-hairline bg-white px-4 font-mono text-[13px] text-ink-strong outline-none focus:border-ink-faint" />
                <button type="submit" className="h-9 rounded-full bg-ink-strong px-4 text-[13px] font-medium text-white hover:bg-[#2a2a2e]">Show</button>
              </form>
            }
          >
            <FramedCard>
              {data?.wallet_error ? <p className="py-8 text-center text-ink-muted">{data.wallet_error}</p>
                : data?.wallet ? (
                  <>
                    <WalletTotals label="All positions" t={data.wallet.totals} />
                    <WalletTotals label="Followed Horizon" t={data.wallet.followed} />
                    <WalletTotals label="Your own" t={data.wallet.own} />
                    <div className="mt-4 border-t border-hairline-soft pt-3">
                      {data.wallet.positions.slice(0, 30).map((p, i) => (
                        <div key={i} className="grid grid-cols-[1fr_auto] items-center gap-x-3 border-t border-hairline-soft py-2 text-[13px] tabular-nums first:border-t-0">
                          <span className="min-w-0 truncate" title={p.title}>{p.title}<span className="text-ink-faint"> · {p.outcome} · {p.open ? `${cents(p.avg_price ?? 0)} → ${cents(p.cur_price ?? 0)}` : "closed"}</span>
                            {p.tag === "followed" ? <span className="ml-2 rounded-full bg-up-tint px-2 py-[2px] text-[11px] font-semibold text-up">Horizon pick</span> : null}</span>
                          <span className={`font-semibold ${(p.unrealized_usd ?? 0) + p.realized_usd >= 0 ? "text-up" : "text-down"}`}>{usd((p.unrealized_usd ?? 0) + p.realized_usd)}</span>
                        </div>
                      ))}
                    </div>
                    <p className="mt-2 text-[12px] text-ink-faint">{data.wallet.note}{data.wallet.truncated ? " Showing the first 1,000 closed positions." : ""}</p>
                  </>
                ) : <p className="py-8 text-center text-ink-muted">No wallet added. Paste a public address above.</p>}
            </FramedCard>
          </Section>
        </div>
      </main>
    </>
  );
}
