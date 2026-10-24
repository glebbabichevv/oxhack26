"""Decision Journal: every call a user (or the extension) acts on, kept with what Horizon said at the time,
scored against the real resolution once the market closes.

  POST /api/journal   one record (known fields only, validated, rate-limited)
  GET  /api/journal?me=<install_id>&limit=50   newest first, with outcome + result_per_dollar once resolved

Record fields (client): install_id (random per install, no PII), ts (ISO, when the decision was made),
market_id (Gamma conditionId 0x… or numeric id), slug, question, side (YES | NO | null for NO_TRADE),
price (what one share of the side taken costs, 0-1; for NO_TRADE the YES price), q / q_low / q_high (Horizon's
YES probability and 10-90% band), action (BUY_YES | BUY_NO | NO_TRADE), stake_usd, kelly_fraction, source, status.
Server adds: id, received_at, outcome (1 = YES won, 0 = NO won, null = open), result_per_dollar
(+1/price - 1 if the side taken won, -1 if it lost; before fees; null for NO_TRADE or open).

Storage (JOURNAL_STORE): "blob" = one private Vercel Blob object per record (needs BLOB_READ_WRITE_TOKEN; append
never races), "file" = JSON lines at JOURNAL_FILE (default /tmp, per instance: a demo fallback that does not
persist on Vercel). Default: blob when the token is set, else file.
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

GAMMA = "https://gamma-api.polymarket.com"
BLOB_API = "https://blob.vercel-storage.com"
PREFIX = "journal/"
MAX_BODY = 4096
RATE = {"ip": (20, 60), "install": (120, 3600)}  # (max requests, per seconds)
OUTCOME_TTL = 600  # re-check an open market at most every 10 min

router = APIRouter()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    install_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    ts: str
    market_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    slug: Optional[str] = Field(None, max_length=200, pattern=r"^[a-z0-9-]*$")
    question: str = Field(min_length=1, max_length=300)
    side: Optional[Literal["YES", "NO"]] = None
    price: float = Field(gt=0, lt=1)
    q: Optional[float] = Field(None, ge=0, le=1)
    q_low: Optional[float] = Field(None, ge=0, le=1)
    q_high: Optional[float] = Field(None, ge=0, le=1)
    action: Literal["BUY_YES", "BUY_NO", "NO_TRADE"]
    stake_usd: Optional[float] = Field(None, ge=0, le=100_000)
    kelly_fraction: Optional[float] = Field(None, ge=0, le=1)
    source: Optional[str] = Field(None, max_length=32, pattern=r"^[a-z0-9_-]*$")
    status: Optional[str] = Field(None, max_length=32, pattern=r"^[a-z0-9_-]*$")

    @field_validator("ts")
    @classmethod
    def _ts(cls, v):
        try:
            t = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("ts must be ISO 8601")
        if t.tzinfo is None:
            raise ValueError("ts needs a timezone (e.g. 2026-10-24T18:00:00Z)")
        now = datetime.now(timezone.utc)
        if not now - timedelta(days=30) <= t <= now + timedelta(minutes=5):
            raise ValueError("ts must be within the last 30 days")
        return t.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------- stores ----------

class BlobStore:
    name = "vercel-blob"

    def __init__(self, token):
        self.token = token
        self.cache = {}  # pathname -> record (records are immutable)
        self.listed_at, self.paths = 0.0, []

    def _req(self, method, url, data=None, headers=None):
        h = {"authorization": f"Bearer {self.token}", "x-api-version": "11", **(headers or {})}
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=h), timeout=10) as r:
            return r.read()

    def put(self, rec):
        path = f"{PREFIX}{rec['received_at'].replace(':', '').replace('-', '')[:15]}-{rec['id']}.json"
        self._req("PUT", f"{BLOB_API}/?pathname={urllib.parse.quote(path)}", json.dumps(rec).encode(),
                  {"x-content-type": "application/json", "x-add-random-suffix": "0", "x-vercel-blob-access": "private"})
        self.cache[path] = rec
        self.paths.append((path, None))

    def all(self):
        if time.time() - self.listed_at > 15:
            paths, cursor = [], None
            while True:
                q = {"prefix": PREFIX, "limit": 1000, **({"cursor": cursor} if cursor else {})}
                page = json.loads(self._req("GET", f"{BLOB_API}?{urllib.parse.urlencode(q)}"))
                paths += [(b["pathname"], b["url"]) for b in page.get("blobs", [])]
                cursor = page.get("cursor")
                if not page.get("hasMore") or not cursor:
                    break
            self.paths, self.listed_at = paths, time.time()
        missing = [(p, u) for p, u in self.paths if p not in self.cache and u]

        def fetch(pu):
            try:
                return pu[0], json.loads(self._req("GET", pu[1]))
            except Exception:  # noqa: BLE001 - one unreadable blob must not hide the rest
                return pu[0], None

        with ThreadPoolExecutor(16) as pool:
            for p, rec in pool.map(fetch, missing):
                if rec:
                    self.cache[p] = rec
        return list(self.cache.values())


class FileStore:
    name = "file"

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def put(self, rec):
        with self.lock, open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def all(self):
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]


def make_store():
    kind = os.environ.get("JOURNAL_STORE") or ("blob" if os.environ.get("BLOB_READ_WRITE_TOKEN") else "file")
    if kind == "blob":
        return BlobStore(os.environ["BLOB_READ_WRITE_TOKEN"])
    return FileStore(os.environ.get("JOURNAL_FILE", "/tmp/horizon-journal.jsonl"))


STORE = make_store()


# ---------- rate limit ----------

_hits, _hits_lock = {}, threading.Lock()


def _allow(key, kind):
    limit, window = RATE[kind]
    now = time.time()
    with _hits_lock:
        recent = [t for t in _hits.get(key, []) if now - t < window]
        if len(recent) >= limit:
            _hits[key] = recent
            return False
        _hits[key] = recent + [now]
        return True


# ---------- outcomes ----------

_outcomes = {}  # market_id -> (checked_at, outcome or None)


def _resolution(m):
    if not m.get("closed") or (m.get("umaResolutionStatus") or "resolved") != "resolved":
        return None
    try:
        prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
    except (TypeError, ValueError):
        return None
    return 1 if prices[:2] == [1.0, 0.0] else 0 if prices[:2] == [0.0, 1.0] else None


def _gamma(params):
    url = f"{GAMMA}/markets?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"User-Agent": "horizon-journal/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def outcomes(market_ids):
    now = time.time()
    due = [m for m in set(market_ids)
           if m not in _outcomes or (_outcomes[m][1] is None and now - _outcomes[m][0] > OUTCOME_TTL)]
    hexes, nums = [m for m in due if m.startswith("0x")], [m for m in due if m.isdigit()]
    found = {}
    try:
        for i in range(0, len(hexes), 50):
            for m in _gamma([("condition_ids", c) for c in hexes[i:i + 50]] + [("closed", "true"), ("limit", 50)]):
                found[m.get("conditionId")] = _resolution(m)
        for i in range(0, len(nums), 50):
            for m in _gamma([("id", c) for c in nums[i:i + 50]] + [("closed", "true"), ("limit", 50)]):
                found[str(m.get("id"))] = _resolution(m)
        for m in due:
            _outcomes[m] = (now, found.get(m))
    except Exception:  # noqa: BLE001 - Gamma down: serve what we know, retry next time
        pass
    return {m: _outcomes.get(m, (0, None))[1] for m in market_ids}


def scored(rec, outcome):
    out = {**rec, "outcome": outcome, "result_per_dollar": None, "right": None}
    if outcome is None or rec.get("action") == "NO_TRADE" or rec.get("side") not in ("YES", "NO"):
        return out
    won = (outcome == 1) == (rec["side"] == "YES")
    out["right"] = won
    out["result_per_dollar"] = round(1 / rec["price"] - 1, 4) if won else -1.0
    return out


# ---------- endpoints ----------

@router.post("/api/journal")
async def add(request: Request):
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, f"record larger than {MAX_BODY} bytes")
    try:
        rec = Record.model_validate_json(body)
    except Exception as e:  # pydantic ValidationError or bad JSON
        raise HTTPException(422, str(e)[:800])
    if rec.action != "NO_TRADE" and rec.side is None:
        raise HTTPException(422, "side is required for BUY_YES / BUY_NO")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0]
    if not _allow(f"ip:{ip}", "ip") or not _allow(f"id:{rec.install_id}", "install"):
        raise HTTPException(429, "too many journal entries, slow down")
    out = {**rec.model_dump(), "id": secrets.token_hex(6),
           "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        STORE.put(out)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"journal storage unavailable ({type(e).__name__})")
    return {"ok": True, "id": out["id"], "storage": STORE.name}


@router.get("/api/journal")
def feed(me: Optional[str] = None, limit: int = 50):
    limit = max(1, min(int(limit), 200))
    try:
        recs = [r for r in STORE.all() if isinstance(r, dict) and r.get("market_id") and r.get("action")]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"journal storage unavailable ({type(e).__name__})")
    if me:
        recs = [r for r in recs if r.get("install_id") == me]
    recs.sort(key=lambda r: (r.get("ts") or "", r.get("received_at") or ""), reverse=True)
    page = recs[:limit]
    res = outcomes([r["market_id"] for r in page])
    page = [scored(r, res.get(r["market_id"])) for r in page]
    if not me:  # the global feed does not expose install ids
        page = [{k: v for k, v in r.items() if k != "install_id"} for r in page]
    done = [r for r in page if r["result_per_dollar"] is not None]
    return {
        "storage": STORE.name, "me": me, "n_total": len(recs), "n_shown": len(page),
        "summary": {"n_trades": sum(r["action"] != "NO_TRADE" for r in page), "n_resolved": len(done),
                    "n_right": sum(bool(r["right"]) for r in done),
                    "mean_result_per_dollar": round(sum(r["result_per_dollar"] for r in done) / len(done), 4) if done else None},
        "records": page,
        "note": "result_per_dollar is per $1 staked on the side taken, before fees; price = cost of one share of that side.",
    }
