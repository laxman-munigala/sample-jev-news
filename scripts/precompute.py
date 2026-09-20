#!/usr/bin/env python3
"""scripts/precompute.py — judge everything once, so a fresh clone opens with results in it.

    uv run python scripts/precompute.py              # everything not yet judged
    uv run python scripts/precompute.py --redo       # re-judge everything
    uv run python scripts/precompute.py --only news --limit 10

The rows this writes are committed with the database. That is what makes the app useful without
an API key: someone you share this with can read every judgment, see the probabilities, and
compare two stories before deciding whether to get a key of their own.

Judgments are stored under the CONCRETE model version the API names (`jev-1.13.0`), never the
`jev-latest` alias that was requested — so a future version's judgments land beside these instead
of silently replacing them.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jevlab import db as store                                  # noqa: E402
from jevlab.jev import JevClient, JevError                      # noqa: E402
from jevlab.jev.client import DEFAULTS                          # noqa: E402
from jevlab.qsets import news, x_ai, x_stocks                   # noqa: E402

TARGETS = {
    "news": ("news", news.SET, lambda db: store.news_items(db)),
    "x-stocks": ("x", x_stocks.SET, lambda db: store.x_posts(db, "stocks")),
    "x-ai": ("x", x_ai.SET, lambda db: store.x_posts(db, "ai")),
}


def run(target: str, *, redo: bool, limit: Optional[int], workers: int) -> tuple:
    kind, qset, load = TARGETS[target]
    db = store.connect()
    items = load(db)
    if not redo:
        judged = store.judgments(db, kind, qset.name)
        items = [i for i in items if i["id"] not in judged]
    if limit:
        items = items[:limit]
    if not items:
        print(f"{target:9} · nothing to do")
        return 0, 0, 0.0

    client = JevClient(workers=workers, log=lambda m: None)
    started = time.perf_counter()
    results = client.judge_many([(i["id"], qset.state(i)) for i in items], qset.questions)
    elapsed = time.perf_counter() - started

    failures: List[str] = []
    for r in results:
        if not r.ok:
            failures.append(f"  #{r.key}: {r.error}")
            continue
        store.save_judgment(db, kind, int(r.key), qset.name, r.model, r.answers,
                            qset.to_row(r.answers), input_tokens=r.input_tokens,
                            latency_ms=r.latency_ms)
    ok = len(results) - len(failures)
    cost = client.input_tokens / 1e6 * DEFAULTS["price_per_mtok"]
    print(f"{target:9} · {ok}/{len(results)} judged by {client.stored_model} in {elapsed:5.1f}s "
          f"({len(results) / elapsed:4.1f}/s) · {client.input_tokens:,} tokens · ${cost:.4f}"
          + (f" · {len(failures)} FAILED" if failures else ""))
    for f in failures:
        print(f)
    db.close()
    return ok, client.input_tokens, elapsed


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=list(TARGETS), action="append",
                    help="just one target (repeatable); default is all three")
    ap.add_argument("--redo", action="store_true", help="re-judge items that already have a row")
    ap.add_argument("--limit", type=int, help="at most N items per target")
    ap.add_argument("--workers", type=int, default=DEFAULTS["workers"])
    args = ap.parse_args(argv)

    try:
        JevClient(workers=1)
    except JevError as e:
        sys.exit(str(e))

    total_ok = total_tokens = 0
    total_time = 0.0
    for target in (args.only or list(TARGETS)):
        ok, tokens, elapsed = run(target, redo=args.redo, limit=args.limit, workers=args.workers)
        total_ok += ok
        total_tokens += tokens
        total_time += elapsed
    print(f"{'total':9} · {total_ok} judgments · {total_tokens:,} input tokens · "
          f"${total_tokens / 1e6 * DEFAULTS['price_per_mtok']:.4f} · {total_time:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
