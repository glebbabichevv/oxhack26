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
    cap, out = total * max_share, [0.0] * len(weights)
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
    return [math.floor(x * 100) / 100 if x >= 1 else 0 for x in out]


class Panel:
    def __init__(self, markets, guard):
        self.m, self.guard, self.plan, self.calls = markets, guard, [], []

    def _side(self, r):
        return {"BUY_YES": "YES", "BUY_NO": "NO"}.get(r["action"])

    def _sug(self, r):
        return max(1.0, math.floor(r["kelly_fraction"] * BANKROLL * 100) / 100)

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
            if self.guard and amt is not None and float(amt) > BANKROLL * MAX_SHARE and not a.get("confirmed_amount") and not a.get("override"):
                return {"error": f"${amt} is over 20% of the budget in one market. To spend a total across several bets call spend_budget; "
                                 "pass confirmed_amount=true only if the user named this amount for this one market."}
            sug = self._sug(r)
            amt = min(float(amt) if amt is not None else sug, BANKROLL)
            self.plan.append({"market": r["slug"], "side": side, "amount": round(amt, 2)})
            return {"added_to_plan": True, "amount": round(amt, 2), "horizon_suggests": sug, "above_suggestion": amt > sug + 0.005,
                    "note": "Horizon will set up this ticket on Polymarket; the user presses Trade"}
        if name == "spend_budget":
            total, mx = float(a.get("total", 0)), min(max(int(a.get("max_bets", 10)), 1), 40)
            if total < 1:
                return {"error": "total must be at least $1"}
            picks = [p for p in self._run("scan_markets", {"tag": a.get("tag", "all"), "within_hours": a.get("within_hours", 24), "top": max(mx * 2, 10)})["picks"]
                     if p["verdict"] != "WAIT"][:mx]
            if not picks:
                return {"total": total, "planned_total": 0, "note": "No good bets right now: Horizon would wait and spend nothing."}
            amts, bets = split_budget(total, [max(p["suggested_bet"], 1) for p in picks]), []
            for p, x in zip(picks, amts):
                if x:
                    self._run("place_bet", {"market": p["market"], "side": p["side"], "amount": x, "confirmed_amount": True})
                    bets.append({"market": p["market"], "side": p["side"], "amount": x})
            spent, sug = round(sum(b["amount"] for b in bets), 2), round(sum(p["suggested_bet"] for p in picks), 2)
            return {"total": total, "planned_total": spent, "unspent": round(total - spent, 2), "bets": bets, "horizon_suggests_total": sug,
                    "rule": "split by Horizon's suggested bets, at most 20% of the total in one market, one bet per event",
                    "note": (f"Only {len(bets)} good bets: the rest stays unspent rather than piling into one market." if spent < total - 0.005
                             else f"This is more than Horizon's own suggestion (${sug:g}); tell the user." if sug < total else None)}
        if name == "summarize_portfolio":
            return {"budget": BANKROLL, "bets_user_placed": 0, "dollars_in_those_bets": 0, "result_so_far": 0}
        if name == "open_my_results":
            return {"opened": True, "summary": "No decisions recorded yet"}
        if name in ("close_all",):
            return {"added_to_plan": 0}
        if name in ("close_position", "adjust_stake"):
            return {"error": "no such open bet"}
        if name == "set_bankroll":
            return {"ok": True, "budget": a.get("amount")}
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
    p, contents, answer = Panel(markets, guard), [{"role": "user", "parts": [{"text": text}]}], ""
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
    s = json.dumps(obj)
    vals = set()
    for t in re.findall(r"-?\d+(?:\.\d+)?", s):
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
    if re.search(r"\b(placed|bought|executed)\b", answer, re.I) and not re.search(r"\b(not|never|once you|after you)\b[^.]*\b(placed|bought|executed)", answer, re.I):
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
        if panel.plan and biggest > t * MAX_SHARE + 0.01 and len(tradable) > 1:
            issues.append(f"one basket: ${biggest} of ${t} in one market")
        if not panel.plan and tradable:
            issues.append("planned nothing though there are tradable markets")
    if group == "count" and len(panel.plan) > chk["max_bets"]:
        issues.append(f"{len(panel.plan)} bets > {chk['max_bets']} asked")
    if group in ("question", "junk") and panel.plan:
        issues.append(f"added {len(panel.plan)} bets to the plan for a question")
    # invented numbers: every $ amount / % in the answer must come from a tool result or the prompt
    known = _numbers_in([c["result"] for c in panel.calls]) | _numbers_in(text) | {BANKROLL, 1, 5, 20, 25, 34677, 10839, 0}
    bad = []
    for tok in NUM.findall(answer):
        if not (tok.startswith("$") or tok.endswith("%")):
            continue
        v = float(tok.strip("$%").replace(",", ""))
        if not any(abs(v - k) <= max(0.011, abs(k) * 0.01) for k in known):
            bad.append(tok)
    if bad:
        issues.append(f"numbers not from any tool: {bad[:5]}")
    return {"id": pid, "group": group, "prompt": text, "ok": not issues, "issues": issues, "answer": answer,
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
