import { FramedCard, Section } from "@/design/components/Page";

// What we trained and what each one gave us: the spoken list of the pitch, one row per method.
// Numbers are the test-set ones in backend/results and integrations/ (see docs/cheatsheet.pdf for the formulas).
type Row = { name: string; what: string; gave: string; tag: "Shipped" | "Helped" | "No gain" | "Lost" };

const ROWS: Row[] = [
  { name: "Logistic calibration", what: "4 coefficients on price and time to the end", gave: "Beats the market's own price out of time (Brier 0.1297 vs 0.1305). Shows the bias: near the end longshots are underpriced, favourites overpriced; a month out prices are fair.", tag: "Shipped" },
  { name: "Event bootstrap", what: "40 refits on resampled events", gave: "An uncertainty band for every prediction; we bet only when its cautious end clears the costs.", tag: "Shipped" },
  { name: "Quarter Kelly, 5% cap", what: "bet sizing", gave: "Most bets lose (about 70%), so each stake stays small; max drawdown 0.22.", tag: "Shipped" },
  { name: "Event coherence (COH)", what: "probabilities sum to 100% across a match, one bet per event", gave: "From +17¢ to about +30¢ per $1 after fees, with half the drawdown.", tag: "Helped" },
  { name: "Gradient boosting", what: "momentum, legs, book share", gave: "No gain over the simple model.", tag: "No gain" },
  { name: "Beta calibration", what: "Kull et al. 2017", gave: "No better than the simple model.", tag: "No gain" },
  { name: "Isotonic regression", what: "per horizon", gave: "−7.8¢ per $1 vs the simple model, walk-forward.", tag: "Lost" },
  { name: "Hierarchical by domain", what: "partial pooling", gave: "Domain terms overfit.", tag: "No gain" },
  { name: "Shin model (1993)", what: "the betting literature's de-vig", gave: "−10¢ per $1: it assumes overpriced longshots; Polymarket's are underpriced.", tag: "Lost" },
  { name: "Ensembles", what: "mean, log pool, agreement filter", gave: "Model errors were 99% correlated, so averaging added nothing.", tag: "No gain" },
  { name: "Selling early", what: "dynamic exit", gave: "No extra profit, slightly smaller drawdown (0.20 vs 0.23).", tag: "No gain" },
  { name: "Crypto as options", what: "Binance prices", gave: "Worse than the market (Brier 0.1471 vs 0.1399), −16.5¢ per $1.", tag: "Lost" },
];

const TAG: Record<Row["tag"], string> = {
  Shipped: "bg-ink-strong text-white",
  Helped: "bg-up-tint text-up",
  "No gain": "bg-fill-soft text-ink-muted",
  Lost: "bg-down-tint text-down",
};

export function Trained() {
  return (
    <Section
      title="What we trained, and what it gave us"
      lead="Ten models and rules, compared on validation only. The simplest model won; the money came from a rule, one bet per event."
    >
      <FramedCard title="Every method we tried" meta="test set, out of time">
        <div>
          {ROWS.map((r) => (
            <div key={r.name} className="grid grid-cols-[1fr_auto] items-start gap-x-3 border-t border-hairline-soft py-2.5 text-[13px] first:border-t-0">
              <div className="min-w-0">
                <span className="font-semibold text-ink-strong">{r.name}</span>
                <span className="text-ink-faint"> · {r.what}</span>
                <p className="mt-0.5 leading-[1.5] text-ink-muted">{r.gave}</p>
              </div>
              <span className={`mt-0.5 shrink-0 rounded-full px-2.5 py-[3px] text-[12px] font-semibold ${TAG[r.tag]}`}>{r.tag}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[12px] text-ink-faint">Checks: walk-forward month by month (positive in 15 of 17), a placebo where prices are assumed right (−8¢), deflated Sharpe over the 12 rules tried. Formulas: <a className="underline decoration-hairline underline-offset-4" href="https://github.com/glebbabichevv/oxhack26/blob/main/docs/cheatsheet.pdf" target="_blank" rel="noreferrer">cheat sheet (PDF)</a>.</p>
      </FramedCard>
    </Section>
  );
}
