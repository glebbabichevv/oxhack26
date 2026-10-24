# Inbox — Role A

Messages from other agents/teammates to Role A. Newest at the bottom.
Format: `- [HH:MM] from <role>: <what is wrong / what you need> — <file or endpoint>`
When you have handled a message, change `- [` to `- [x]` at its start.

- [x] [14:50] from C (TheMarkz3): pitch is mine (PR #3: integrations/pitch/DEMO_SCRIPT.md + DEVPOST.md, every number from backend/results). calibration_check.py never reached main — PR #3 adds it, since CLAUDE.md credits it. Check: at 24h the 0–10¢ bin resolves YES 3.0% (n=3904), so 'longshots underpriced' is only true ~10–35¢; I phrase it that way — backend/results/calibration.json
- [x] [14:55] from C (Ayaz): fixed the domain mislabel (PR int/domain-fix). Tweet/post-count and mention markets were tagged politics: 3,313 markets / 9,883 rows (a third of "politics") moved to culture; data/horizons.csv + live.csv regenerated, row count unchanged (120,058), all checks pass. **Rerun the model: the politics and culture results will change.** On spread: Polymarket has no historical order book, so resolved markets can only get a cost assumption, not a measured spread. live.csv median spread is 1¢; the 1¢ floor is the honest choice — data/horizons.csv "domain"
- [x] [15:05] from C (TheMarkz3): (1) please confirm by_horizon[].with_costs.mean_return_per_trade is return on stake (per $1 staked). I plotted it as 'mean return per trade after 1¢ cost' and footnoted 'each horizon backtested on its own' because the n_trades sum to more than 7,228. Correct me if wrong. (2) This is our best TIME-theme visual, consider it for the screen: 30d −0.4%, 7d +2.5%, 3d +6.5%, 1d +13.8%, 12h +15.5% — integrations/pitch/when_to_trade.png (PR #3), backend/results/backtest.json
- [15:35] from C (Ayaz): QA: live card "Will Elon Musk post 90–114 tweets…" still shows politics on the screen. Data fix is PR #4; after merging, rerun the model so live.json/calibration.json pick up the new domains — backend/results/live.json
