"""Pitch step 3: the backtest, trade by trade.

    python integrations/backtest_log.py            # -> pitch-proof/3-backtest-trades.csv + 3-backtest-summary.txt

Re-runs backend/model.py evaluate() in memory exactly like integrations/reproduce.py (shipped cutoff, seed 0) and
writes every out-of-time test trade of the shipped policy (COH) with the stake it got after the one-bankroll cap:
when it was entered, the market, how far from the end, market price, Horizon's probability and band, the side,
costs, stake, outcome and result. The summary recomputes the headline from the CSV rows alone, so anyone can
check the +¢ per $1 with a spreadsheet.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import model as M  # noqa: E402

cap = {}
orig = M.robustness


def grab(trades):
    cap["t"] = trades.copy()
    return orig(trades)


M.robustness = grab  # robustness() receives exactly the headline trades
_, _, bt = M.evaluate(M.load_horizons(ROOT / "data" / "horizons.csv"))
t = cap["t"]
_, stake = M.exposure(t, t["kelly"].to_numpy())
t = t.assign(stake=stake)
t = t[t["stake"] > 0]
entry = pd.to_datetime(t["end_date"], utc=True, format="ISO8601") - pd.to_timedelta(t["horizon_hours"], unit="h")
side = np.where(t["action"] == "BUY_YES", "YES", "NO")
paid = np.where(side == "YES", t["price_yes"] + t["cost"], 1 - t["price_yes"] + t["cost"])
won = np.where(side == "YES", t["outcome"] == 1, t["outcome"] == 0)
out = pd.DataFrame({
    "entered_utc": entry.dt.strftime("%Y-%m-%d %H:%M"), "resolved_utc": pd.to_datetime(t["resolved_at"], utc=True).dt.strftime("%Y-%m-%d %H:%M"),
    "event": t[M.event_key(t)], "market_id": t["market_id"], "question": t["question"], "domain": t["domain"],
    "hours_before_end": t["horizon_hours"], "market_price_yes": t["price_yes"].round(4),
    "horizon_q_yes": t["q"].round(4), "side": side, "cost_per_share": t["cost"].round(4),
    "paid_per_share": np.round(paid, 4), "net_edge": t["edge"].round(4),
    "stake_bankrolls": t["stake"].round(5), "outcome_yes": t["outcome"].astype(int), "won": won,
    "return_per_dollar": t["ret"].round(4), "pnl_bankrolls": (t["stake"] * t["ret"]).round(5),
}).sort_values("entered_utc")
dst = ROOT / "pitch-proof"
dst.mkdir(exist_ok=True)
out.to_csv(dst / "3-backtest-trades.csv", index=False)

h = bt["headline"]
per_dollar = (out["pnl_bankrolls"].sum() / out["stake_bankrolls"].sum())
lines = [
    f"Backtest, out of time: trained on markets that ended before {bt['cutoff']}, tested on the {bt['n_test_markets']:,} after.",
    f"Policy {h['policy']}: within 24 h of the end, net edge >= 1¢ after spread + Polymarket fee, probabilities summing to 1 "
    "across an event's outcomes, one bet per event, ¼ Kelly capped 5%, open stake <= 1 bankroll.",
    "",
    f"Trades in the CSV          {len(out):,}   (headline {h['n_trades']:,})",
    f"Won                        {out['won'].mean():.1%}",
    f"Result per $1 staked       {per_dollar * 100:+.1f}¢  recomputed from the CSV   (headline {h['per_dollar'] * 100:+.1f}¢, 90% CI "
    f"{h['per_dollar_ci'][0] * 100:+.1f}¢ to {h['per_dollar_ci'][1] * 100:+.1f}¢)",
    f"Total, starting bankrolls  {out['pnl_bankrolls'].sum():+.2f}   (headline {h['return']:+.2f})",
    f"First / last entry         {out['entered_utc'].iloc[0]}  /  {out['entered_utc'].iloc[-1]}",
    "",
    "By domain (¢ per $1, trades):",
]
for d, g in out.groupby("domain"):
    lines.append(f"  {d:<14} {g['pnl_bankrolls'].sum() / g['stake_bankrolls'].sum() * 100:+6.1f}¢  {len(g):>5}")
lines += ["", "Biggest wins and losses (per $1):"]
for _, r in pd.concat([out.nlargest(3, "pnl_bankrolls"), out.nsmallest(3, "pnl_bankrolls")]).iterrows():
    lines.append(f"  {r['entered_utc']}  {r['side']:<3} at {r['paid_per_share'] * 100:4.0f}¢  {r['return_per_dollar']:+6.2f}  {r['question'][:70]}")
lines += ["", f"Every row: pitch-proof/3-backtest-trades.csv"]
(dst / "3-backtest-summary.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
