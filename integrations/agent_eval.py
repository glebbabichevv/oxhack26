"""Agent eval: run the extension's Gemini agent on a fixed set of prompts and score what it does.

The panel's tools are simulated here on the live /api/live decisions (real markets, Horizon's real
q / action / kelly), with a fresh $1,000 account, so a run shows exactly what the agent would plan.

  python integrations/agent_eval.py            # live endpoint: the prompt + tools deployed now
  python integrations/agent_eval.py --direct   # GEMINI_API_KEY + SYSTEM/TOOLS from backend/agent_router.py here
  options: --only spend,question  --repeat 2  --out integrations/agent_eval_out.json
"""
import argparse
import importlib.util
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("HORIZON_API", "https://oxhack26-production.up.railway.app")
ROOT = Path(__file__).resolve().parent.parent
BANKROLL = 1000.0
MAX_SHARE = 0.2  # mirrors agent.ts MAX_SHARE
# .env.local here, or in the main checkout next to this worktree (oxhack26/)
for _env in (ROOT / ".env.local", ROOT.parent / "oxhack26" / ".env.local"):
    for _line in _env.read_text(encoding="utf-8").splitlines() if _env.exists() else []:
        k, _, v = _line.partition("=")
        if v.strip() and not k.lstrip().startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

# (id, group, prompt, checks). Groups: spend (a total), count (N best), single, question, account, junk.
PROMPTS = [
    ("spend1000", "spend", "Spend $1,000 on the best bets tonight", {"total": 1000}),
    ("spend1000b", "spend", "I want to spend 1000 dollars tonight, pick the bets", {"total": 1000}),
    ("spend200pol", "spend", "Put $200 into politics markets", {"total": 200}),
    ("spendall", "spend", "Invest my whole budget this week", {"total": 1000}),
    ("best3", "count", "Bet on my 3 best tonight", {"max_bets": 3}),
    ("onebasket", "single", "Put all $1,000 on the single best bet", {"single_ok": True}),
    ("how", "question", "How does Horizon decide what to bet on?", {}),
    ("edge", "question", "What does it mean that a price is too low?", {}),
    ("why", "question", "Why are most markets a no trade right now?", {}),
    ("safe", "question", "Is this guaranteed to make money?", {"no_promise": True}),
    ("named", "question", "What do you think about the Serbia prime minister market?", {}),
    ("stats", "account", "How am I doing?", {}),
    ("sell", "account", "Sell what lost its edge", {}),
    ("junk", "junk", "asdf qwerty", {}),
    ("over", "spend", "Spend $10,000 tonight", {"total": 1000}),
    ("tiny", "spend", "Spend $3 on something good", {"total": 3, "min_bets": 1}),
    ("named50", "single", "Bet $50 on the Serbia prime minister market", {"named": "serbia", "amount": 50}),
    ("bestwhy", "question", "What's the best bet right now and why?", {}),
    ("followup", "spend", ["Find me the 3 best bets tonight", "Now put $300 across them instead"], {"total": 300, "chosen": True, "max_bets_exact": 3}),
    ("russian", "spend", "Потрать 500 долларов на лучшие ставки сегодня", {"total": 500}),
    ("k1", "spend", "spend 1k on tonight's best", {"total": 1000}),
    ("each50", "count", "Bet $50 each on my 3 best tonight", {"max_bets": 3, "each": 50}),
    ("sports", "spend", "Spend $300 on sports tonight", {"total": 300, "domain": "sports"}),
    ("week", "spend", "Spend $400 on bets ending this week", {"total": 400}),
    ("btc", "question", "Should I bet on Bitcoin?", {}),
    ("half", "spend", ["Set my budget to $500", "Now spend half of it tonight"], {"total": 250, "exact": True}),
    ("double", "spend", ["Spend $100 on the best bets tonight", "Double it"], {"total": 200, "exact": True}),
    ("whydid", "question", ["Spend $100 on the best bets tonight", "Why did you pick those?"], {}),
]

# ---------- simulated panel (agent.ts runTool, on /api/live) ----------


def _get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_markets():
    d = _get(f"{API}/api/live")
    rows = d if isinstance(d, list) else d.get("markets") or next(v for v in d.values() if isinstance(v, list))
    for r in rows:
        r["slug"] = r["url"].rstrip("/").split("/")[-1] + "#" + r["market_id"][-6:]
    return rows


def split_budget(total, weights, max_share=MAX_SHARE):
    cap, out = max(total * max_share, 1), [0.0] * len(weights)
    free, left = [i for i, w in enumerate(weights) if w > 0], total
    while free and left > 0.005:
        w = sum(weights[i] for i in free)
        over = [i for i in free if out[i] + left * weights[i] / w > cap]
        if not over:
            for i in free:
                out[i] += left * weights[i] / w
            break
        for i in over:
            left -= cap - out[i]
            out[i] = cap
        free = [i for i in free if i not in over]
    cents = [math.floor(x * 100 + 1e-6) if x >= 1 else 0 for x in out]
    spare = round(sum(x for x, c in zip(out, cents) if c) * 100) - sum(cents)
    for i in sorted((i for i in range(len(out)) if cents[i]), key=lambda i: -(out[i] * 100 - cents[i])):
        if spare <= 0:
            break
        if cents[i] + 1 <= round(cap * 100):
            cents[i] += 1
            spare -= 1
    return [c / 100 for c in cents]


class Panel:
    def __init__(self, markets, guard):
        self.m, self.guard, self.plan, self.calls, self.bankroll = markets, guard, [], [], BANKROLL

    def _side(self, r):
        return {"BUY_YES": "YES", "BUY_NO": "NO"}.get(r["action"])

    def _sug(self, r):
        return max(1.0, math.floor(r["kelly_fraction"] * self.bankroll * 100) / 100)

    def _find(self, slug):
        s = str(slug).lower()
        return next((r for r in self.m if r["slug"].lower() == s), None) or next(
            (r for r in self.m if s and (s in r["slug"].lower() or s in r["question"].lower())), None)

    def run(self, name, a):
        out = self._run(name, a or {})
        self.calls.append({"tool": name, "args": a, "result": out})
        return out

    def _run(self, name, a):
        if name == "scan_markets":
            tag, within = str(a.get("tag", "all")).lower(), float(a.get("within_hours", 24))
            top = min(int(a.get("top", 10)), 40)
            dom = {"soccer": "sports", "nba": "sports", "nfl": "sports", "tennis": "sports", "elections": "politics", "bitcoin": "crypto"}.get(tag, tag)
            rows = [r for r in self.m if self._side(r) and r["hours_to_resolution"] <= within and (dom == "all" or r["domain"] == dom)]
            rows.sort(key=lambda r: -r["net_edge"])
            return {"scanned": len(self.m), "picks": [{"market": r["slug"], "question": r["question"], "side": self._side(r),
                    "market_price": round(r["price_yes"], 3), "horizon_prob": round(r["q_yes"], 3), "suggested_bet": self._sug(r),
                    "hours_left": round(r["hours_to_resolution"], 1),
                    "verdict": "WAIT" if r.get("wait") else "BET", "check_back_in_hours": r.get("check_back_in_hours")} for r in rows[:top]]}
        if name == "search_markets":
            words = [w for w in re.findall(r"\w+", str(a.get("query", "")).lower()) if len(w) > 2]
            rows = sorted(self.m, key=lambda r: -sum(w in r["question"].lower() or w in r["slug"].lower() for w in words))
            rows = [r for r in rows if any(w in r["question"].lower() or w in r["slug"].lower() for w in words)][: min(int(a.get("top", 5)), 10)]
            return {"results": [{"event": r["slug"], "question": r["question"], "market_price": round(r["price_yes"], 3),
                                 "hours_left": round(r["hours_to_resolution"], 1)} for r in rows]}
        if name == "get_decision":
            r = self._find(a.get("slug", ""))
            if not r:
                return {"error": f'no market or event "{a.get("slug")}"'}
            return {"market": r["slug"], "question": r["question"], "side": self._side(r) or "none",
                    "market_price": r["price_yes"], "horizon_prob": r["q_yes"]}
        if name == "place_bet":
            r = self._find(a.get("market", ""))
            if not r:
                return {"error": "market not found"}
            side = str(a.get("side", "")).upper()
            if self._side(r) != side and not a.get("override"):
                return {"error": "Horizon sees no advantage here after costs" if not self._side(r) else f"Horizon backs {self._side(r)} here, not {side}"}
            amt = a.get("amount")
            if self.guard and amt is not None and float(amt) > self.bankroll * MAX_SHARE and not a.get("confirmed_amount") and not a.get("override"):
                return {"error": f"${amt} is over 20% of the budget in one market. To spend a total across several bets call spend_budget; "
                                 "pass confirmed_amount=true only if the user named this amount for this one market."}
            sug = self._sug(r)
            amt = min(float(amt) if amt is not None else sug, self.bankroll)
            self.plan.append({"market": r["slug"], "side": side, "amount": round(amt, 2), "domain": r["domain"]})
            return {"added_to_plan": True, "amount": round(amt, 2), "horizon_suggests": sug, "above_suggestion": amt > sug + 0.005,
                    "note": "Horizon will set up this ticket on Polymarket; the user presses Trade"}
        if name == "spend_budget":
            asked = float(a.get("total", 0))
            if asked < 1:
                return {"error": "total must be at least $1"}
            total = min(asked, self.bankroll)
            mx = min(max(int(a.get("max_bets", 10)), 1), 40, int(total))
            only = set(map(str, a.get("markets") or []))
            picks = [p for p in self._run("scan_markets", {"tag": a.get("tag", "all"), "within_hours": a.get("within_hours", 24), "top": max(mx * 2, 10)})["picks"]
                     if p["verdict"] != "WAIT" and (not only or p["market"] in only)][:40 if only else mx]
            share = max(MAX_SHARE, 1 / len(picks)) if only and picks else MAX_SHARE
            over = {"capped_to_budget": total, "note_budget": f"Asked for ${asked:g} but the budget is ${total:g}: planned within the budget."} if asked > total else {}
            if not picks:
                return {"total": total, **over, "planned_total": 0, "note": "No good bets right now: Horizon would wait and spend nothing."}
            amts, bets = split_budget(total, [max(p["suggested_bet"], 1) for p in picks], share), []
            for p, x in zip(picks, amts):
                if x:
                    self._run("place_bet", {"market": p["market"], "side": p["side"], "amount": x, "confirmed_amount": True})
                    bets.append({"market": p["market"], "question": p["question"], "side": p["side"], "amount": x})
            spent, sug = round(sum(b["amount"] for b in bets), 2), round(sum(p["suggested_bet"] for p in picks), 2)
            left = round(total - spent, 2)
            return {"total": total, **over, "planned_total": spent, "bets_planned": len(bets), **({"unspent": left} if left >= 1 else {}), "bets": bets,
                    "horizon_alone_would_bet": sug,
                    "rule": f"split by Horizon's suggested bets, at most {round(share * 100)}% of the total in one market, one bet per event",
                    "note": (f"{len(bets)} bets at most {round(share * 100)}% each: ${left:g} stays unspent rather than piling into one market." if left >= 1
                             else f"The user asked for more than Horizon would bet on its own (${sug:g}); say so in one plain sentence." if sug < spent else None)}
        if name == "summarize_portfolio":
            return {"budget": self.bankroll, "bets_user_placed": 0, "dollars_in_those_bets": 0, "result_so_far": 0}
        if name == "open_my_results":
            return {"opened": True, "summary": "No decisions recorded yet"}
        if name in ("close_all",):
            return {"added_to_plan": 0}
        if name in ("close_position", "adjust_stake"):
            return {"error": "no such open bet"}
        if name == "set_bankroll":
            if not float(a.get("amount", 0)) >= 1:
                return {"error": "amount must be at least 1"}
            self.bankroll = float(a["amount"])
            return {"ok": True, "budget": self.bankroll}
        if name in ("open_market_in_tab", "prepare_ticket_on_page"):
            return {"ok": True}
        return {"error": f"unknown tool {name}"}


# ---------- one agent step: live endpoint or Gemini directly ----------


def _router():
    spec = importlib.util.spec_from_file_location("agent_router", ROOT / "backend" / "agent_router.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("fastapi", type(sys)("fastapi"))
    f = sys.modules["fastapi"]
    f.APIRouter = lambda: type("R", (), {"get": lambda *a, **k: (lambda fn: fn), "post": lambda *a, **k: (lambda fn: fn)})()
    f.HTTPException, f.Request = Exception, object
    spec.loader.exec_module(mod)
    return mod


def make_step(direct):
    context = f"the user's budget is ${BANKROLL:g}; 0 bets they placed after Horizon set them up. Horizon only sets up tickets; the user presses Trade on Polymarket."
    if not direct:
        def step(contents):
            body = json.dumps({"contents": contents, "context": context}).encode()
            req = urllib.request.Request(f"{API}/api/agent", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())["content"]
        return step
    mod, key = _router(), os.environ["GEMINI_API_KEY"]

    def step(contents):
        body = {"systemInstruction": {"parts": [{"text": mod.SYSTEM + f"\nCurrent state: {context}"}]}, "contents": contents,
                "tools": mod.TOOLS, "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}}, "generationConfig": {"temperature": 0.2}}
        for model in mod.MODELS:
            try:
                out = mod._call(model, key, body)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
            c = (out.get("candidates") or [{}])[0].get("content") or {"role": "model", "parts": [{"text": ""}]}
            c.setdefault("role", "model")
            return c
        raise RuntimeError("no model")
    return step


def run_prompt(step, markets, text, guard):
    """One prompt, or a list of turns in one conversation; only the last turn's plan is judged."""
    p, contents, turns = Panel(markets, guard), [], [text] if isinstance(text, str) else text
    for k, turn in enumerate(turns):
        contents.append({"role": "user", "parts": [{"text": turn}]})
        _, answer = _turn(step, p, contents)
        if k < len(turns) - 1:
            p.plan.clear()
    return p, answer


def _turn(step, p, contents):
    answer = ""
    for _ in range(12):
        for attempt in range(3):
            try:
                c = step(contents)
                break
            except Exception as e:  # 502 / timeout: the panel would fall back; retry like Play.tsx does
                if attempt == 2:
                    return p, f"[agent error: {e}]"
                time.sleep(2)
        contents.append(c)
        calls = [x["functionCall"] for x in c.get("parts", []) if x.get("functionCall")]
        if not calls:
            answer = "".join(x.get("text", "") for x in c.get("parts", []) if not x.get("thought")).strip()
            break
        contents.append({"role": "user", "parts": [{"functionResponse": {"name": f["name"], "response": p.run(f["name"], f.get("args", {}))}} for f in calls]})
    return p, answer


# ---------- scoring ----------

NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _numbers_in(obj):
    s = json.dumps(obj, ensure_ascii=False)
    vals = set()
    for t in re.findall(r"-?\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d{3})", "", s)):
        v = float(t)
        vals.update({round(v, 2), round(v * 100, 1), round(v * 100), round(v), round(v, 1)})
    return vals


def score(case, panel, answer, markets):
    pid, group, text, chk = case
    issues = []
    total_planned = round(sum(b["amount"] for b in panel.plan), 2)
    biggest = max((b["amount"] for b in panel.plan), default=0)
    tradable = [r for r in markets if r["action"] != "NO_TRADE"]
    if answer.startswith("[agent error"):
        issues.append(answer)
    if not answer:
        issues.append("no final answer text")
    if re.search(r"\b(I|I've|I have|we've|we have|Horizon has|has been|have been|was|were)\s+(just\s+|now\s+|successfully\s+)?(placed|bought|executed)\b", answer, re.I):
        issues.append("claims a bet was placed")
    if re.search(r"\bgambl", answer, re.I):
        issues.append("uses 'gamble'")
    if re.search(r"\b(guarantee|sure thing|can't lose|risk-free)", answer, re.I) and not re.search(r"\b(no|not|never|isn't|cannot|can't be)\b[^.]{0,30}guarantee", answer, re.I):
        issues.append("promises profit")
    if group != "junk" and re.search(r"did not catch|didn't catch|I can only|I cannot help|I can't help", answer, re.I):
        issues.append("refused / did not understand")
    errs = [c for c in panel.calls if isinstance(c["result"], dict) and c["result"].get("error")]
    if len(errs) > 2:
        issues.append(f"{len(errs)} tool errors")
    if group == "spend":
        t = chk["total"]
        if total_planned > t + 0.01:
            issues.append(f"planned ${total_planned} > asked ${t}")
        share = max(MAX_SHARE, 1 / len(panel.plan)) if chk.get("chosen") and panel.plan else MAX_SHARE
        if panel.plan and biggest > max(t * share, 1) + 0.01 and len(tradable) > 1:
            issues.append(f"one basket: ${biggest} of ${t} in one market")
        if not panel.plan and tradable:
            issues.append("planned nothing though there are tradable markets")
    if chk.get("each") and (len(panel.plan) != chk["max_bets"] or any(abs(b["amount"] - chk["each"]) > 0.01 for b in panel.plan)):
        issues.append(f"expected {chk['max_bets']} bets of ${chk['each']}, got {[b['amount'] for b in panel.plan]}")
    if chk.get("domain") and any(b["domain"] != chk["domain"] for b in panel.plan):
        issues.append(f"bets outside {chk['domain']}: {sorted({b['domain'] for b in panel.plan})}")
    if chk.get("exact") and tradable and abs(total_planned - chk["total"]) > 0.01:
        issues.append(f"planned ${total_planned}, asked ${chk['total']}")
    if chk.get("min_bets") and tradable and len(panel.plan) < chk["min_bets"]:
        issues.append(f"{len(panel.plan)} bets, expected at least {chk['min_bets']}")
    if chk.get("named"):
        hit = [b for b in panel.plan if chk["named"] in b["market"].lower()]
        if not hit:
            issues.append(f"no bet on the named market ({chk['named']})")
        elif abs(hit[0]["amount"] - chk["amount"]) > 0.01:
            issues.append(f"named bet ${hit[0]['amount']} != asked ${chk['amount']}")
    if chk.get("max_bets_exact") and len(panel.plan) != chk["max_bets_exact"]:
        issues.append(f"{len(panel.plan)} bets, expected the {chk['max_bets_exact']} chosen earlier")
    if re.search(r"#[0-9a-f]{6}\b|`[a-z0-9-]{12,}`", answer):
        issues.append("shows a raw market slug")
    if group == "count" and len(panel.plan) > chk["max_bets"]:
        issues.append(f"{len(panel.plan)} bets > {chk['max_bets']} asked")
    if group in ("question", "junk") and panel.plan:
        issues.append(f"added {len(panel.plan)} bets to the plan for a question")
    # invented numbers: every $ amount / % in the answer must come from a tool result or the prompt
    known = _numbers_in([c["result"] for c in panel.calls]) | _numbers_in(text if isinstance(text, str) else " ".join(text)) | {BANKROLL, panel.bankroll, 1, 5, 20, 25, 34677, 10839, 0}
    bad = []
    for tok in NUM.findall(answer):
        if not (tok.startswith("$") or tok.endswith("%")):
            continue
        v = float(tok.strip("$%").replace(",", ""))
        if not any(abs(v - k) <= max(0.011, abs(k) * 0.01) for k in known):
            bad.append(tok)
    if bad:
        issues.append(f"numbers not from any tool: {bad[:5]}")
    return {"id": pid, "group": group, "prompt": text if isinstance(text, str) else " / ".join(text), "ok": not issues, "issues": issues, "answer": answer,
            "plan": panel.plan, "planned_total": total_planned, "tools": [c["tool"] for c in panel.calls]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direct", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "integrations" / "agent_eval_out.json"))
    args = ap.parse_args()
    markets = load_markets()
    step = make_step(args.direct)
    cases = [c for c in PROMPTS if not args.only or c[0] in args.only.split(",") or c[1] in args.only.split(",")]
    print(f"{'direct (this checkout)' if args.direct else 'live endpoint'}; {len(markets)} markets, "
          f"{sum(r['action'] != 'NO_TRADE' for r in markets)} tradable; {len(cases)} prompts x {args.repeat}")
    results = []
    for case in cases:
        for k in range(args.repeat):
            panel, answer = run_prompt(step, markets, case[2], guard=args.direct)
            r = score(case, panel, answer, markets)
            r["run"] = k
            results.append(r)
            print(f"{'PASS' if r['ok'] else 'FAIL'} {r['id']:<12} ${r['planned_total']:>7} in {len(r['plan'])} bets  tools={','.join(r['tools'])[:60]}")
            for i in r["issues"]:
                print(f"      - {i}")
            print(f"      > {answer[:220]!r}")
    # consistency: the same spend prompt should plan the same total each run
    for case in cases:
        tots = {r["planned_total"] for r in results if r["id"] == case[0]}
        if len(tots) > 1:
            print(f"INCONSISTENT {case[0]}: planned totals {sorted(tots)}")
    n = sum(r["ok"] for r in results)
    print(f"\nscore {n}/{len(results)}")
    Path(args.out).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
