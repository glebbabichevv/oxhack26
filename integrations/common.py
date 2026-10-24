"""Shared Polymarket helpers for the Horizon data pipeline (Role C)."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "horizon-oxhack26/1.0"

# First matching group wins, so order is priority: a Fed market tagged both
# "politics" and "economy" is economics; an election market tagged "world" is politics.
DOMAIN_TAGS = [
    # Tweet-count / "will X say Y" markets carry a "politics" tag too but are culture bets.
    ("culture", {"tweets-markets", "elon-tweets", "mentions", "mention-markets"}),
    ("sports", {"sports", "nba", "nfl", "nhl", "mlb", "soccer", "football", "basketball", "tennis",
                "golf", "ufc", "mma", "boxing", "f1", "formula-1", "cricket", "esports", "epl",
                "champions-league", "ncaa", "cbb", "cfb", "baseball", "hockey", "chess", "games"}),
    ("crypto", {"crypto", "bitcoin", "ethereum", "solana", "crypto-prices", "xrp", "memecoins",
                "airdrops", "stablecoins", "defi", "nft"}),
    ("economics", {"economy", "fed", "fed-rates", "fomc", "finance", "business", "stocks",
                   "economic-policy", "inflation", "cpi", "gdp", "jobs-report", "interest-rates",
                   "tariffs", "recession", "commodities", "ipos", "earnings", "big-tech"}),
    ("politics", {"politics", "elections", "us-politics", "us-election", "global-elections",
                  "trump", "congress", "senate", "house", "supreme-court", "courts",
                  "trump-presidency", "primaries", "world-elections", "uk", "france", "germany"}),
    ("geopolitics", {"geopolitics", "world", "middle-east", "ukraine", "russia", "israel", "iran",
                     "china", "gaza", "military-strikes", "war", "nato", "ceasefire"}),
    ("science_tech", {"tech", "ai", "science", "space", "openai", "elon-musk", "climate",
                      "weather", "pandemics", "health"}),
    ("culture", {"pop-culture", "celebrities", "culture", "entertainment", "movies", "music",
                 "awards", "oscars", "grammys", "tv", "youtube", "twitter", "tweets-markets",
                 "mentions", "box-office", "religion"}),
]


def domain_of(tag_slugs):
    slugs = set(tag_slugs)
    for domain, keys in DOMAIN_TAGS:
        if slugs & keys:
            return domain
    return "other"


def tag_slugs(market):
    slugs = [t.get("slug", "") for t in market.get("tags") or []]
    for event in market.get("events") or []:
        slugs += [t.get("slug", "") for t in event.get("tags") or []]
    return [s for s in slugs if s]


def get(url, params=None, tries=8):
    for attempt in range(tries):
        wait = min(60, 2 * 2 ** attempt)
        try:
            r = SESSION.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                wait = max(wait, float(r.headers.get("Retry-After") or 0))
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == tries - 1:
                raise
            time.sleep(wait)


def parse_ts(s):
    """Polymarket mixes '2024-11-05T12:00:00Z' and '2024-11-06 15:17:41+00'."""
    if not s:
        return None
    s = s.replace(" ", "T").replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_yes_no(market):
    try:
        return [o.lower() for o in json.loads(market.get("outcomes") or "[]")] == ["yes", "no"]
    except ValueError:
        return False


def yes_token(market):
    return json.loads(market["clobTokenIds"])[0]
