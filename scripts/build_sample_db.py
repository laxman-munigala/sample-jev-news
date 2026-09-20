#!/usr/bin/env python3
"""scripts/build_sample_db.py — how `data/sample.db` was made. You do not need to run this.

The sample database is committed to the repo, so a clone has its data already. This script is
kept for provenance: it shows exactly which rows were copied out of the private research database
this demo was carved from, and how they were curated.

    uv run python scripts/build_sample_db.py --source /path/to/app.db

Curation matters more than volume here. 100 news stories picked at random would be 60 near-identical
analyst notes; jev would answer them all the same way and the demo would teach nothing. So both
tables are filled by QUOTA over buckets chosen to make the model's discrimination visible — a
price-move recap next to a genuine disclosure, a 12-ticker roundup next to a single-company filing,
an unconfirmed "reportedly" next to a company press release. Every bucket is a case where one of
the questions in `jevlab/qsets/` should swing hard.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "sample.db"

# ─────────────────────────────────────────────────────────────────── schema

SCHEMA = """
CREATE TABLE news_items (
    id             INTEGER PRIMARY KEY,   -- 1..100, the display order
    story_id       TEXT UNIQUE NOT NULL,
    published_et   TEXT NOT NULL,
    source         TEXT,
    headline       TEXT NOT NULL,
    summary        TEXT,
    body           TEXT,
    url            TEXT,
    subject_ticker TEXT NOT NULL,         -- the company the judgment is ABOUT
    subject_name   TEXT,
    other_tickers  TEXT NOT NULL,         -- JSON array: the story's other tags
    bucket         TEXT NOT NULL          -- why this story is in the sample
);

CREATE TABLE x_posts (
    id            INTEGER PRIMARY KEY,    -- 1..100, the display order
    post_id       TEXT UNIQUE NOT NULL,
    feed          TEXT NOT NULL,          -- 'stocks' | 'ai'  -> which question set applies
    author_handle TEXT,
    author_name   TEXT,
    verified      INTEGER DEFAULT 0,
    posted_at_et  TEXT,
    text          TEXT NOT NULL,
    quote_text    TEXT,
    url           TEXT,
    likes         INTEGER DEFAULT 0,
    replies       INTEGER DEFAULT 0,
    reposts       INTEGER DEFAULT 0,
    bookmarks     INTEGER DEFAULT 0,
    views         INTEGER DEFAULT 0,
    cashtags      TEXT NOT NULL DEFAULT '[]',   -- JSON array, stocks feed
    bucket        TEXT NOT NULL
);

-- Every judgment ever made, cached. The app reads this first and only calls the API when you
-- ask it to; a re-run under the same (item, question set, model) replaces the row.
CREATE TABLE judgments (
    item_kind    TEXT NOT NULL,           -- 'news' | 'x'
    item_id      INTEGER NOT NULL,
    qset         TEXT NOT NULL,           -- 'jev-news-v1' | 'jev-x-stocks-v1' | 'jev-x-ai-v1'
    model        TEXT NOT NULL,           -- the CONCRETE version the API named, never the alias
    answers_json TEXT NOT NULL,           -- {question_id: raw typed answer}
    row_json     TEXT NOT NULL,           -- the question set's to_row() projection
    input_tokens INTEGER DEFAULT 0,
    latency_ms   INTEGER DEFAULT 0,
    judged_at    TEXT NOT NULL,
    PRIMARY KEY (item_kind, item_id, qset, model)
);

CREATE INDEX judgments_item ON judgments(item_kind, item_id);
"""

# ───────────────────────────────────────────────────────── news curation

# (bucket, quota, headline pattern). Order matters: a story lands in the FIRST bucket it matches,
# so the narrow, interesting buckets are listed before the broad ones.
NEWS_BUCKETS: List[Tuple[str, int, str]] = [
    ("price_move", 12,
     r"^why (is|are) |stock (surg|tumbl|jump|slid|soar|sink|climb|drop|plung|rally|pop)|"
     r"shares (surg|tumbl|jump|slid|soar|sink|climb|drop|plung|rally|pop)|what'?s going on with|"
     r"moving in|movers|trading (higher|lower)|hits? (new )?(all-time|52-week)"),
    ("roundup", 8, r"^\d+ |top \d|these \d|\b\d+ (stocks|etfs|names)\b|stocks to watch|"
                   r"biggest (movers|gainers|losers)"),
    ("transcript", 6, r"transcript|earnings (conference )?call"),
    ("earnings", 10, r"\bq[1-4]\b|earnings|results|beat|miss(es|ed)?\b|revenue|eps\b"),
    ("analyst", 10, r"analyst|upgrade|downgrade|price target|initiat|rating|bullish on|"
                    r"no longer bullish|forecasts?"),
    ("m_and_a", 8, r"acquir|merger|takeover|buyout|to buy |stake in|divest|spin-?off|"
                   r"\bdeal\b|acquisition"),
    ("speculation", 8, r"reportedly|rumou?r|is said to|sources say|may |could |eyes |weighs|"
                       r"considering|in talks|explores?"),
    ("regulatory_legal", 8, r"fda|lawsuit|sued|court|judge|settle|probe|investigat|sec |doj|"
                            r"antitrust|approval|regulat|subpoena|fine"),
    ("product_contract", 8, r"launch|unveil|announce|partnership|contract|order|wins?\b|"
                            r"rollout|debut|introduc"),
    ("guidance_capital", 8, r"guidance|outlook|warns?|forecast|offering|buyback|dividend|"
                            r"dilut|raises? \$|files? for"),
    ("leadership", 6, r"\bceo\b|\bcfo\b|chief execu|steps down|appoint|resign|board of"),
    ("macro_other", 8, r".*"),
]

# Crypto / FX tags Alpaca mixes into `symbols_json`; never a judgment's subject company.
_NOT_EQUITY = re.compile(r"(USD|USDT|EUR|GBP|JPY)$|^\$|[^A-Z.]")
_TOKENS = {"BTC", "ETH", "XRP", "SOL", "ADA", "DOGE", "ARB", "OP", "AVAX", "LINK", "DOT", "LTC",
           "BCH", "TRX", "TON", "SUI", "APT", "SEI", "PURR", "HYPE", "ZEC", "XMR", "SHIB", "PEPE",
           "BNB", "MATIC", "ATOM", "NEAR", "ICP", "FIL", "UNI", "AAVE", "MKR", "CRV", "USDC"}

# Company names for the tickers that ended up in the sample. The research DB only names the 40
# tickers it tracks; the rest are filled here so `subject_company` reads like a company and not a
# symbol — it is part of the state jev judges.
NAMES: Dict[str, str] = {
    "AAPL": "Apple Inc.", "ADBE": "Adobe Inc.", "AMD": "Advanced Micro Devices, Inc.",
    "AMZN": "Amazon.com, Inc.", "AVGO": "Broadcom Inc.", "BA": "The Boeing Company",
    "BABA": "Alibaba Group Holding Limited", "BAC": "Bank of America Corporation",
    "C": "Citigroup Inc.", "COIN": "Coinbase Global, Inc.", "COST": "Costco Wholesale Corporation",
    "CRM": "Salesforce, Inc.", "CRWD": "CrowdStrike Holdings, Inc.",
    "CSCO": "Cisco Systems, Inc.", "CTSH": "Cognizant Technology Solutions Corporation",
    "CVS": "CVS Health Corporation", "DAL": "Delta Air Lines, Inc.",
    "DDOG": "Datadog, Inc.", "DIS": "The Walt Disney Company", "F": "Ford Motor Company",
    "FDX": "FedEx Corporation", "GE": "GE Aerospace", "GM": "General Motors Company",
    "GOOG": "Alphabet Inc.", "GOOGL": "Alphabet Inc.", "GS": "The Goldman Sachs Group, Inc.",
    "HD": "The Home Depot, Inc.", "HIMS": "Hims & Hers Health, Inc.",
    "HOOD": "Robinhood Markets, Inc.", "IBM": "International Business Machines Corporation",
    "INTC": "Intel Corporation", "JPM": "JPMorgan Chase & Co.", "KO": "The Coca-Cola Company",
    "LLY": "Eli Lilly and Company", "LMT": "Lockheed Martin Corporation",
    "MA": "Mastercard Incorporated", "MCD": "McDonald's Corporation",
    "MDB": "MongoDB, Inc.", "META": "Meta Platforms, Inc.", "MRNA": "Moderna, Inc.",
    "MSFT": "Microsoft Corporation", "MU": "Micron Technology, Inc.",
    "NBIS": "Nebius Group N.V.", "NET": "Cloudflare, Inc.", "NFLX": "Netflix, Inc.",
    "NKE": "NIKE, Inc.", "NOW": "ServiceNow, Inc.", "NVDA": "NVIDIA Corporation",
    "ORCL": "Oracle Corporation", "PEP": "PepsiCo, Inc.", "PFE": "Pfizer Inc.",
    "PG": "The Procter & Gamble Company", "PLTR": "Palantir Technologies Inc.",
    "PYPL": "PayPal Holdings, Inc.", "QCOM": "QUALCOMM Incorporated",
    "RDDT": "Reddit, Inc.", "RIVN": "Rivian Automotive, Inc.", "SBUX": "Starbucks Corporation",
    "SHOP": "Shopify Inc.", "SMCI": "Super Micro Computer, Inc.", "SNOW": "Snowflake Inc.",
    "SOFI": "SoFi Technologies, Inc.", "SQ": "Block, Inc.", "T": "AT&T Inc.",
    "TEAM": "Atlassian Corporation", "TGT": "Target Corporation", "TSLA": "Tesla, Inc.",
    "TSM": "Taiwan Semiconductor Manufacturing Company Limited", "TTD": "The Trade Desk, Inc.",
    "TXN": "Texas Instruments Incorporated", "U": "Unity Software Inc.",
    "UBER": "Uber Technologies, Inc.", "UNH": "UnitedHealth Group Incorporated",
    "UPST": "Upstart Holdings, Inc.", "V": "Visa Inc.", "WMT": "Walmart Inc.",
    "XOM": "Exxon Mobil Corporation",
    # ETFs and funds that show up as a story's only tag
    "QQQ": "Invesco QQQ Trust", "SPY": "SPDR S&P 500 ETF Trust", "IWM": "iShares Russell 2000 ETF",
    "GLD": "SPDR Gold Shares", "IGV": "iShares Expanded Tech-Software Sector ETF",
    "USO": "United States Oil Fund",
}


# Benzinga names a company the same way every time: "Rocket Lab Corp (NASDAQ:RKLB)". That is the
# most reliable source of a real company name for the ~80 tickers outside the research universe.
_EXCHANGE_NAME = (r"([A-Z][A-Za-z0-9.,&'’/-]*(?:\s+[A-Za-z0-9.,&'’/-]+){{0,5}})\s*"
                  r"\((?:NASDAQ|NYSE|NYSEAMERICAN|AMEX|OTC(?:QB|QX)?|CBOE|BATS)[:\s]*{sym}\s*\)")


def _name_from_text(symbol: str, *parts: Optional[str]) -> Optional[str]:
    """The company name as the wire itself wrote it, pulled out of the story text."""
    pat = re.compile(_EXCHANGE_NAME.format(sym=re.escape(symbol)))
    for part in parts:
        m = pat.search(part or "")
        if m:
            name = " ".join(m.group(1).split()).strip(" .,-")
            # Strip a leading sentence fragment: keep the last few Capitalised words.
            words = name.split()
            while words and not words[0][:1].isupper():
                words.pop(0)
            name = " ".join(words[-6:])
            name = re.sub(r"^(Shares of|shares of|of|The stock of)\s+", "", name)
            if 2 <= len(name) <= 60:
                return name
    return None


def _equities(symbols: List[str]) -> List[str]:
    out = []
    for s in symbols:
        s = (s or "").strip().upper()
        if 1 <= len(s) <= 5 and not _NOT_EQUITY.search(s) and s not in _TOKENS \
                and s not in out:
            out.append(s)
    return out


def _subject(symbols: List[str], headline: str, body: str) -> Optional[str]:
    """Which tagged company the judgment is ABOUT.

    A story's tag list is not ranked, so the first tag is often a bystander. Prefer the ticker the
    headline actually talks about; fall back to a company this demo can name; only then to the
    first tag. Roundups deliberately fall through to that last case — "one of nineteen names in a
    movers list" is precisely the state the `relevance` question exists to catch.
    """
    candidates = _equities(symbols)
    if not candidates:
        return None
    head = headline or ""

    def rank(sym: str) -> tuple:
        in_head = bool(re.search(rf"\b{re.escape(sym)}\b", head))
        named = NAMES.get(sym)
        name_in_head = bool(named and re.search(
            re.escape(named.split(" Inc")[0].split(",")[0].split(" Corp")[0]), head, re.I))
        body_name = bool(_name_from_text(sym, head))
        return (in_head, name_in_head, body_name, bool(named), -candidates.index(sym))

    return max(candidates, key=rank)


def pick_news(src: sqlite3.Connection, limit: int = 100) -> List[Dict[str, Any]]:
    src.row_factory = sqlite3.Row
    rows = src.execute("""
        SELECT story_id, created_at, created_ms, headline, summary, author, source, url,
               symbols_json, body
          FROM news_stories
         WHERE body IS NOT NULL AND length(body) > 500
         ORDER BY created_ms DESC
    """).fetchall()

    quotas = {name: n for name, n, _ in NEWS_BUCKETS}
    patterns = [(name, re.compile(pat, re.I)) for name, _, pat in NEWS_BUCKETS]
    picked: Dict[str, List[Dict[str, Any]]] = {name: [] for name in quotas}
    seen_subject: Dict[str, int] = {}

    for r in rows:
        symbols = json.loads(r["symbols_json"] or "[]")
        subject = _subject(symbols, r["headline"], r["body"])
        if not subject:
            continue
        # Spread the sample over companies: at most 4 stories about any one ticker.
        if seen_subject.get(subject, 0) >= 4:
            continue
        head = r["headline"]
        for name, pat in patterns:
            if len(picked[name]) >= quotas[name]:
                continue
            if pat.search(head):
                picked[name].append({
                    "story_id": r["story_id"], "published_et": r["created_at"],
                    "source": r["source"], "headline": head, "summary": r["summary"],
                    "body": r["body"], "url": r["url"], "subject_ticker": subject,
                    "subject_name": (NAMES.get(subject)
                                     or _name_from_text(subject, head, r["summary"], r["body"])),
                    "bucket": name,
                    "other_tickers": json.dumps([s for s in symbols if s != subject][:24]),
                })
                seen_subject[subject] = seen_subject.get(subject, 0) + 1
                break
        if sum(len(v) for v in picked.values()) >= limit:
            break

    out: List[Dict[str, Any]] = []
    for name, _, _ in NEWS_BUCKETS:
        out.extend(picked[name])
    return out[:limit]


# ───────────────────────────────────────────────────────── X curation

CASHTAG = re.compile(r"\$([A-Z]{1,5})(?![A-Za-z0-9])")

# The two X lists the posts were scraped from, and the question set each one gets.
FEEDS = {"stocks": (3, 5), "ai": (1, 2, 4)}

X_BUCKETS: Dict[str, List[Tuple[str, int, str]]] = {
    "stocks": [
        ("ticker_call", 16, r"\$[A-Z]{1,5}\b"),
        ("macro_take", 8, r"market|fed|rates?|inflation|tariff|bitcoin|crypto|yields?|"
                          r"sector|breadth|spx|indices"),
        ("trading_lesson", 10, r"\b(i |my |you |lesson|learn|rule|mistake|discipline|risk|"
                               r"psychology|patience|portfolio)\b"),
        ("promo_noise", 6, r"subscrib|join|members|link in bio|dm |course|free trial|code:"),
        ("chatter", 10, r".*"),
    ],
    "ai": [
        ("model_release", 10, r"released?|launch|announc|introduc|new model|available now|"
                              r"open-?sourc|ship(ped|ping)?|drop(ped|s)?\b|v\d"),
        ("benchmark_claim", 10, r"benchmark|\d+(\.\d+)?%|sota|beats?|outperform|score|eval|"
                                r"tokens?/s|latency|accuracy"),
        ("jev_typesafe", 10, r"\bjev\b|typesafe|system one|noul\b"),
        ("industry_news", 8, r"openai|anthropic|google|meta|nvidia|funding|ipo|valuation|"
                             r"hiring|report(ed|s)?\b|\$\d+[bm]\b"),
        ("hot_take", 12, r".*"),
    ],
}


def pick_x(src: sqlite3.Connection, per_feed: int = 50) -> List[Dict[str, Any]]:
    src.row_factory = sqlite3.Row
    out: List[Dict[str, Any]] = []
    for feed, batches in FEEDS.items():
        placeholders = ",".join("?" * len(batches))
        rows = src.execute(f"""
            SELECT p.* FROM x_posts p
              JOIN x_batch_posts b USING(post_id)
             WHERE b.batch_id IN ({placeholders})
               AND length(trim(coalesce(p.text,''))) > 40
             GROUP BY p.post_id
             ORDER BY p.likes DESC, p.post_id
        """, batches).fetchall()

        specs = X_BUCKETS[feed]
        quotas = {n: q for n, q, _ in specs}
        patterns = [(n, re.compile(p, re.I)) for n, _, p in specs]
        picked: Dict[str, List[Dict[str, Any]]] = {n: [] for n in quotas}
        per_author: Dict[str, int] = {}

        for r in rows:
            handle = r["author_handle"] or ""
            # No single account may own more than a fifth of a feed's sample.
            if per_author.get(handle, 0) >= per_feed // 5:
                continue
            text = r["text"] or ""
            for name, pat in patterns:
                if len(picked[name]) >= quotas[name]:
                    continue
                if pat.search(text):
                    picked[name].append({
                        "post_id": r["post_id"], "feed": feed, "author_handle": handle,
                        "author_name": r["author_name"], "verified": r["verified"] or 0,
                        "posted_at_et": r["posted_at_et"], "text": text,
                        "quote_text": r["quote_text"], "url": r["url"],
                        "likes": r["likes"] or 0, "replies": r["replies"] or 0,
                        "reposts": r["reposts"] or 0, "bookmarks": r["bookmarks"] or 0,
                        "views": r["views"] or 0, "bucket": name,
                        "cashtags": json.dumps(sorted(set(CASHTAG.findall(text)))),
                    })
                    per_author[handle] = per_author.get(handle, 0) + 1
                    break
            if sum(len(v) for v in picked.values()) >= per_feed:
                break

        feed_rows: List[Dict[str, Any]] = []
        for name, _, _ in specs:
            feed_rows.extend(picked[name])

        # A bucket can come up short (few posts match `promo_noise`). Top the feed back up to its
        # target from whatever is left, so both feeds are exactly `per_feed` rows.
        if len(feed_rows) < per_feed:
            have = {r["post_id"] for r in feed_rows}
            catch_all = specs[-1][0]
            for r in rows:
                if len(feed_rows) >= per_feed:
                    break
                if r["post_id"] in have:
                    continue
                text = r["text"] or ""
                feed_rows.append({
                    "post_id": r["post_id"], "feed": feed, "author_handle": r["author_handle"] or "",
                    "author_name": r["author_name"], "verified": r["verified"] or 0,
                    "posted_at_et": r["posted_at_et"], "text": text,
                    "quote_text": r["quote_text"], "url": r["url"],
                    "likes": r["likes"] or 0, "replies": r["replies"] or 0,
                    "reposts": r["reposts"] or 0, "bookmarks": r["bookmarks"] or 0,
                    "views": r["views"] or 0, "bucket": catch_all,
                    "cashtags": json.dumps(sorted(set(CASHTAG.findall(text)))),
                })
                have.add(r["post_id"])
        out.extend(feed_rows[:per_feed])
    return out


# ───────────────────────────────────────────────────────── write

def build(source: Path, dest: Path, keep_judgments: bool = True) -> None:
    if not source.exists():
        sys.exit(f"source database not found: {source}")

    cached: List[tuple] = []
    if keep_judgments and dest.exists():
        old = sqlite3.connect(dest)
        try:
            cached = old.execute("SELECT * FROM judgments").fetchall()
        except sqlite3.OperationalError:
            pass
        old.close()

    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    news, posts = pick_news(src), pick_x(src)
    src.close()

    dest.unlink(missing_ok=True)
    db = sqlite3.connect(dest)
    db.executescript(SCHEMA)
    for i, row in enumerate(news, 1):
        cols = ", ".join(row)
        db.execute(f"INSERT INTO news_items (id, {cols}) VALUES (?, {','.join('?' * len(row))})",
                   [i, *row.values()])
    for i, row in enumerate(posts, 1):
        cols = ", ".join(row)
        db.execute(f"INSERT INTO x_posts (id, {cols}) VALUES (?, {','.join('?' * len(row))})",
                   [i, *row.values()])
    if cached:
        db.executemany(f"INSERT OR REPLACE INTO judgments VALUES ({','.join('?' * len(cached[0]))})",
                       cached)
    db.commit()

    def count(sql: str) -> List[tuple]:
        return db.execute(sql).fetchall()

    print(f"{dest.relative_to(ROOT)}: {len(news)} news · {len(posts)} X posts "
          f"· {len(cached)} cached judgments carried over")
    print("  news buckets:  " + ", ".join(
        f"{b}={n}" for b, n in count("SELECT bucket, count(*) FROM news_items GROUP BY 1")))
    print("  x buckets:     " + ", ".join(
        f"{f}/{b}={n}" for f, b, n in
        count("SELECT feed, bucket, count(*) FROM x_posts GROUP BY 1,2")))
    db.close()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path,
                    default=Path.home() / "projects/stock-research-skill/data/app.db",
                    help="the research database the sample is carved from")
    ap.add_argument("--dest", type=Path, default=DEST)
    ap.add_argument("--drop-judgments", action="store_true",
                    help="do not carry the cached judgments over into the rebuilt file")
    args = ap.parse_args(argv)
    build(args.source, args.dest, keep_judgments=not args.drop_judgments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
