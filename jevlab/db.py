#!/usr/bin/env python3
"""jevlab/db.py — the sample database: 100 news stories, 100 X posts, and every judgment made.

Three tables, no ORM, no migrations. `data/sample.db` is committed to the repository, so a fresh
clone has both the data and the judgments that were pre-computed against it — the app is fully
browsable before anyone has an API key.

    news_items   100 Benzinga stories, each with the company the judgment is ABOUT
    x_posts      100 X posts, 50 from a markets list and 50 from an AI list
    judgments    one row per (item, question set, model). A live re-run REPLACES its row.

Judgments are keyed by the **concrete** model version the API named (`jev-1.13`), never the alias
that was requested (`jev-latest`). When TypeSafe ships a new version, its judgments land beside
the old ones instead of quietly overwriting them, and the app can show you both.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sample.db"

_JSON_COLUMNS = {"other_tickers", "cashtags"}


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def _row(r: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    out = dict(r)
    for col in _JSON_COLUMNS & out.keys():
        out[col] = json.loads(out[col] or "[]")
    return out


# ───────────────────────────────────────────────────────────────── items

def news_items(db: sqlite3.Connection) -> List[Dict[str, Any]]:
    return [_row(r) for r in db.execute("SELECT * FROM news_items ORDER BY id")]


def news_item(db: sqlite3.Connection, item_id: int) -> Optional[Dict[str, Any]]:
    return _row(db.execute("SELECT * FROM news_items WHERE id = ?", (item_id,)).fetchone())


def x_posts(db: sqlite3.Connection, feed: Optional[str] = None) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM x_posts" + (" WHERE feed = ?" if feed else "") + " ORDER BY id"
    return [_row(r) for r in db.execute(sql, (feed,) if feed else ())]


def x_post(db: sqlite3.Connection, item_id: int) -> Optional[Dict[str, Any]]:
    return _row(db.execute("SELECT * FROM x_posts WHERE id = ?", (item_id,)).fetchone())


def item(db: sqlite3.Connection, kind: str, item_id: int) -> Optional[Dict[str, Any]]:
    return news_item(db, item_id) if kind == "news" else x_post(db, item_id)


# ─────────────────────────────────────────────────────────── judgments

def judgment(db: sqlite3.Connection, kind: str, item_id: int, qset: str,
             model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The cached judgment for one item, newest model first unless one is named."""
    sql = ("SELECT * FROM judgments WHERE item_kind = ? AND item_id = ? AND qset = ?"
           + (" AND model = ?" if model else "") + " ORDER BY judged_at DESC LIMIT 1")
    args = (kind, item_id, qset) + ((model,) if model else ())
    r = db.execute(sql, args).fetchone()
    if r is None:
        return None
    out = dict(r)
    out["answers"] = json.loads(out.pop("answers_json"))
    out["row"] = json.loads(out.pop("row_json"))
    return out


def judgments(db: sqlite3.Connection, kind: str, qset: str) -> Dict[int, Dict[str, Any]]:
    """Every cached judgment for one (kind, question set), by item id."""
    out: Dict[int, Dict[str, Any]] = {}
    for r in db.execute("SELECT * FROM judgments WHERE item_kind = ? AND qset = ? "
                        "ORDER BY judged_at", (kind, qset)):
        d = dict(r)
        d["answers"] = json.loads(d.pop("answers_json"))
        d["row"] = json.loads(d.pop("row_json"))
        out[d["item_id"]] = d
    return out


def save_judgment(db: sqlite3.Connection, kind: str, item_id: int, qset: str, model: str,
                  answers: Dict[str, Any], row: Dict[str, Any], *, input_tokens: int = 0,
                  latency_ms: int = 0) -> None:
    db.execute("""
        INSERT INTO judgments (item_kind, item_id, qset, model, answers_json, row_json,
                               input_tokens, latency_ms, judged_at)
             VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT (item_kind, item_id, qset, model) DO UPDATE SET
            answers_json = excluded.answers_json, row_json = excluded.row_json,
            input_tokens = excluded.input_tokens, latency_ms = excluded.latency_ms,
            judged_at    = excluded.judged_at
    """, (kind, item_id, qset, model, json.dumps(answers), json.dumps(row),
          input_tokens, latency_ms, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    db.commit()


def coverage(db: sqlite3.Connection) -> List[Dict[str, Any]]:
    """One row per question set: how many items it has judged, and by which model."""
    return [dict(r) for r in db.execute("""
        SELECT qset, model, count(*) AS judged, sum(input_tokens) AS input_tokens,
               round(avg(latency_ms)) AS avg_latency_ms, max(judged_at) AS last_run
          FROM judgments GROUP BY qset, model ORDER BY qset, model
    """)]
