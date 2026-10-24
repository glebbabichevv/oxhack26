# Inbox — Role A

Messages from other agents/teammates to Role A. Newest at the bottom.
Format: `- [HH:MM] from <role>: <what is wrong / what you need> — <file or endpoint>`
When you have handled a message, change `- [` to `- [x]` at its start.

- [14:40] from C (Ayaz): `data/horizons_full.csv` is 11x larger than horizons.csv (34,677 markets, 120k rows, ≥$100k volume, 2024-01 → 2026-10) with the same endDate anchor and event_id. 720h has 9.5k rows. Your test set of 955 markets could become ~14.7k with a 2026-04-01 cutoff. Note: Fed markets are `economics` there (not politics), so re-check the "only politics" claim before switching. Run: `python backend/model.py` with the data dir pointed at the _full files — integrations/README.md "Full dataset"
