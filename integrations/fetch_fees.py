"""Polymarket taker fee schedule per market -> data/fees.csv (for the model's cost).

Run from the repo root:  python integrations/fetch_fees.py

Gamma's feeSchedule is exact per market: taker fee per share = rate * (p * (1 - p)) ** exponent,
makers pay nothing. Older markets have fees off. Caveat: this is the schedule *now*; the API keeps
no history, so a market whose rate changed after our horizon timestamp is priced at today's rate.
"""
import json

import pandas as pd

from common import DATA, GAMMA, get


def fetch(ids, closed):
    rows = {}
    for i in range(0, len(ids), 100):
        params = [("limit", 100), ("closed", closed)] + [("condition_ids", c) for c in ids[i:i + 100]]
        for m in get(f"{GAMMA}/markets", params) or []:
            fs = m.get("feeSchedule") or {}
            on = bool(m.get("feesEnabled")) and bool(fs)
            rows[m["conditionId"]] = dict(
                market_id=m["conditionId"], fees_enabled=on, fee_type=m.get("feeType") or "",
                fee_rate=float(fs.get("rate") or 0) if on else 0.0, fee_exponent=float(fs.get("exponent") or 1),
                taker_only=bool(fs.get("takerOnly", True)))
    return rows


def main():
    hz = pd.read_csv(DATA / "horizons.csv", usecols=["market_id"]).market_id.unique().tolist()
    live = pd.read_csv(DATA / "live.csv", usecols=["market_id"]).market_id.unique().tolist()
    rows = fetch(hz, "true")
    rows.update(fetch([m for m in live if m not in rows], "false"))
    df = pd.DataFrame(rows.values())
    df.to_csv(DATA / "fees.csv", index=False)
    print(f"wrote {len(df)} markets ({len(hz) + len(live)} asked) to {DATA / 'fees.csv'}")
    print(df.groupby(["fees_enabled", "fee_rate"]).size().to_string())


if __name__ == "__main__":
    main()
