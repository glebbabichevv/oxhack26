# Inbox — Role A

Messages from other agents/teammates to Role A. Newest at the bottom.
Format: `- [HH:MM] from <role>: <what is wrong / what you need> — <file or endpoint>`
When you have handled a message, change `- [` to `- [x]` at its start.

- [14:55] from C (Ayaz): fixed the domain mislabel (PR int/domain-fix). Tweet/post-count and mention markets were tagged politics: 3,313 markets / 9,883 rows (a third of "politics") moved to culture; data/horizons.csv + live.csv regenerated, row count unchanged (120,058), all checks pass. **Rerun the model: the politics and culture results will change.** On spread: Polymarket has no historical order book, so resolved markets can only get a cost assumption, not a measured spread. live.csv median spread is 1¢; the 1¢ floor is the honest choice — data/horizons.csv "domain"
