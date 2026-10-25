# Horizon — pitch script (Gleb + Ayaz)

About 2.5 minutes of talking, then questions.
Lines in *italics* are what you do on screen. Everything else is what you say.

---

## Setup (before the judges arrive)

*Gleb's laptop, three tabs open:*
- *Tab 1: the site, scrolled to the very top (the arrows).*
- *Tab 2: a Polymarket match that ends 12–24 hours from now. Horizon side panel open, budget set to $100–500.*
- *Tab 3: the journal page, scrolled to "Sealed before the outcomes".*

*Backup video open in the background. Phone hotspot ready.*

---

## 1. Gleb — the idea

*Tab 1 is on screen. Point at the arrows.*

**Gleb:**
Hi, we're Horizon.
You've probably seen headlines like "Polymarket gives this a 15% chance." People treat that as a real probability.
We checked if it actually is. We looked at 34,000 Polymarket markets that have already closed.

*Drag the time slider slowly from 30 days to 12 hours.*

**Gleb:**
A month before a market closes, the prices are pretty fair. The arrows are flat.
But as the end gets closer, people get too confident. Cheap outcomes win more often than their price says.
The arrows show how we correct the price. The dots show what actually happened.

Ayaz built the model and the testing, so he'll explain how it works.

---

## 2. Ayaz — the model and the proof

*Scroll down to the headline numbers.*

**Ayaz:**
The model is small on purpose. It only looks at two things: the price, and how much time is left.
It learned from past markets how far off the crowd usually is at each point in time.

Before we settled on it, we compared it with eleven alternatives, on 4,768 validation markets, without touching the test set:
gradient boosting, a logistic regression with extra features like price momentum, volatility and order-book depth,
beta calibration, isotonic regression, a hierarchical model with a separate slope for each market type,
Shin's model and the power method from the betting literature, an average of all the models,
a filter that only bets when every model agrees, and a pool where each model's weight depends on the time left.

None of the bigger models beat the simple one. Their errors were 99% correlated, because they all read the same price.
But one variant from that search did win: making the probabilities of all outcomes of a match add up to 100%,
and placing only one bet per match. That's the rule we use now, and it took us from 17 to about 30 cents per dollar.

We tested it on 10,000 markets the model had never seen.
After Polymarket's fees, it made about 30 cents for every dollar bet.
It was profitable in 15 out of 17 months.

*Scroll to the red and green dots (Long run).*

**Ayaz:**
To be clear, most of our bets lose. It only works over hundreds of bets.

That's the evidence. Gleb will show you how you actually use it.

---

## 3. Gleb — the demo

*Switch to Tab 2 (the Polymarket match). Point at the Horizon card.*

**Gleb:**
This is a real match on Polymarket.
The market says [p]. Horizon says [q]. So the price is too low, and it suggests putting in [k] dollars.

*Click the button. The order ticket fills in.*

**Gleb:**
It fills in the order for me. I press Trade myself, because it's my money.

*Type into the agent box: "Set up my 3 best bets tonight". Wait for the plan.*

**Gleb:**
There's also an agent. It makes a plan.
One bet is ready now. One it's waiting on, because it's still too early. One it skips, because it's the same match.

This bet won't settle until tonight, and one bet doesn't tell you much anyway. So here's how we know it's not luck.

---

## 4. Gleb — the capsule

*Switch to Tab 3 (journal, sealed section).*

**Gleb:**
Every decision Horizon makes lands in this journal, with the time and the price, including every "no".

Yesterday afternoon, before any of these markets closed, we saved our predictions on 359 live markets.
We posted the file's fingerprint in the hackathon Discord, so we couldn't change it afterwards.
We also wrote down in advance what we expected.
We opened it at 12:30. Here's what happened.

*Read the result off the screen, whatever it says.*

*Back to Tab 1, scroll to "No edge here".*

**Gleb:**
We're also open about where it doesn't work. Culture markets lose money, crypto is about break-even,
and we don't give advice in the last 12 hours, because we never tested there.

That's Horizon. Happy to take any questions.

---

## Questions

**Ayaz answers:** overfitting, validation, the ten models, the placebo test, the formula, the papers.
**Gleb answers:** the product, the agent, the capsule, fees and capacity, why a human presses Trade, the UK, what's next, "did you build this in 24 hours?"

Don't talk over each other. If someone forgets a number, the other adds one sentence after.

Short answers:
- **Did you overfit?** We split by time, picked the model on a validation set, and opened the test set only for the final two. It's profitable in 15 of 17 months.
- **What if the prices were right?** We replayed the same bets with fair outcomes 1,000 times. You lose about 10 cents per dollar. None came close to our result.
- **Fees?** Every bet pays that market's own Polymarket fee plus half the spread. It still works with double fees.
- **How much money can it take?** About $10,000 per market on big football markets, about $1,000 on typical ones.
- **Why such a simple model?** Bigger models weren't better. All of them make almost the same mistakes, because they all look at the same price.
- **Is this machine learning?** Yes, a small one: a logistic regression learned from 23,000 markets. The agent is the AI part, and it takes every number from the model.
- **Where does it fail?** Culture loses money, crypto is about zero, and we don't advise under 12 hours to the end.
- **Did you build this in 24 hours?** The browser layer is my own code from before. The model, data, rules, capsule and integration were built here.

---

## If something breaks

- **No internet:** Gleb turns on the phone hotspot. Ayaz keeps talking about the model meanwhile.
- **Extension or agent hangs:** play the backup video. Don't fix it in front of the judges.
- **Card says "Not sure here":** "This market closes too soon. We never tested under 12 hours, so it won't advise." Switch to the backup match.
- **Judge is in a hurry:** do only the arrows, "about 30 cents per dollar", and the card on the match.
