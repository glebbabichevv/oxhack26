# Every model, scored separately (Role C, TheMarkz3)

Evaluation only. Nothing here changes `backend/`, the site or the shipped model, and the test set is never scored.
All runs use `backend/playoff.py`'s harness: the same split and embargo, policy V3 (and V0), Polymarket fees, ¼ Kelly capped at 5% per trade and open stake ≤ 1 bankroll.
The ensemble itself is Ayaz's (`integrations/ensemble/` on int/ensemble). These are its inputs and a larger-sample check.

- `evaluate_all.py` scores every member once on validation, the last 20% of train (4,768 markets). Output: `VALIDATION.md`, `results.json`, per-row q / lo / hi in `q_validation.csv.gz`, and unscored test predictions in `q_test_unscored.csv.gz`.
- `walk_forward.py` scores every member walk-forward over **all of train**. There are 7 time blocks, and each is predicted by models fitted only on earlier events. That gives **15,840 markets, 30,875 rows and up to 8,800 trades per model**. Every member is compared with M0 on the same resampled events (paired event bootstrap, 90% CI). Output: `WALK_FORWARD.md`, `walk_forward.json`.

Why not 10,000 V3 trades per model: V3 takes at most one trade per market, and only ~25–30% of markets get one.
All of train is 23,838 markets, so V3 cannot reach 10k without opening the test set. V0 trades more markets, up to ~8,800.

## Walk-forward findings (paired vs M0; a CI that excludes 0 is a real difference)
- **Shin gets Polymarket backwards.**
  - On the 9,335 rows where de-vigging changes the price, Shin is no better than the raw price: Δ log loss +1.0e-3 [−0.0, +2.3].
  - Trading it loses money: V0 −6.9¢ per $1 [−11.9, −2.0] on 670 trades, −23.9¢ vs M0 [−31.1, −17.0].
  - Fitted freely per horizon, Shin's insider share z comes out **negative at every horizon**: 12h −0.072, 24h −0.073, 72h −0.064, 7d −0.048, 30d −0.012. Shin assumes overpriced longshots. The data says underpriced, most strongly near resolution, and about fair a month out.
- **Power method:**
  - de-vig only: no better than the price;
  - with the spread as the overround: worse than the price, Δ +1.0e-3 [+0.8, +1.3];
  - fitted k per horizon is k < 1 everywhere: 0.83 at 12–24h, rising to 0.95 at 30d. That is the same time story. power_fit ≈ M0: Δ ¢/$ +0.8 [−2.9, +4.8].
- **Shin with the spread as overround** equals the market price exactly. For two outcomes, Shin reduces to the additive method, which is a mathematical identity.
- **No difference from M0:** isotonic is worse (log loss +5.5e-3 [+3.8, +7.4], −7.8¢/$). beta, beta_h and hierarchical match or trail M0.
- **Real improvements over M0 (V3, paired):**
  - **mix_4** (mean of M0, M1_lite, M2_lite, beta_h): log loss −4.1e-3 [−5.0, −3.2]; **+7.0¢ per $1 [+2.7, +11.6]**; 3,955 trades.
  - **mix_4+shin:** +8.9¢ [+4.3, +14.1].
  - **M0_coherent:** +6.1¢ [+3.1, +9.2] on 2,686 trades.
  - M1_lite and M2_lite alone beat M0 on log loss (−4.1e-3 and −5.4e-3), but their ¢/$ CIs include 0.
- **Caveat on M1_lite / M2_lite:** their book features (legs in the event, leg's share of the book) count only the legs in our dataset. The dataset keeps markets by **lifetime** volume, so these features may carry a little look-ahead that M0 cannot. Check this before any of them ships. They also lack model_v2's momentum features (no hourly paths on this machine).
