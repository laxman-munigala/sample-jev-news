#!/usr/bin/env python3
"""jevlab/ui/batch_tab.py — a hundred judgments at once, and what that costs.

One item at a time shows you what jev answers. This tab shows you the property that makes it
usable as infrastructure: a judgment is ~600 ms and a fraction of a cent, so classifying an entire
corpus is a coffee break and a rounding error, not a budget line. `judge_many` pools the calls and
keeps failures per item — one bad row cannot take down the pass.

Everything below reads the stored judgments, so the distributions are there before you run
anything.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from jevlab import db as store
from jevlab.jev import JevError
from jevlab.jev.client import DEFAULTS, have_key
from jevlab.qsets import news, x_ai, x_stocks
from jevlab.ui.common import get_client, get_db, session_cost

# dataset label -> (kind, question set, how to load the rows, the columns worth charting)
DATASETS = {
    "News — jev-news-v1": ("news", news.SET, lambda db: store.news_items(db),
                           ["relevance", "timing", "sentiment", "event_type"]),
    "X markets — jev-x-stocks-v1": ("x", x_stocks.SET, lambda db: store.x_posts(db, "stocks"),
                                    ["post_type", "subject", "stance", "horizon"]),
    "X AI — jev-x-ai-v1": ("x", x_ai.SET, lambda db: store.x_posts(db, "ai"),
                           ["topic", "claim_type", "tone"]),
}


def _label(kind: str, item: Dict[str, Any]) -> str:
    if kind == "news":
        return f'{item["subject_ticker"]} · {item["headline"]}'
    return f'@{item["author_handle"]} · ' + " ".join((item["text"] or "").split())[:90]


def _results_frame(kind: str, items: List[Dict[str, Any]],
                   judged: Dict[int, Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        j = judged.get(item["id"])
        if not j:
            continue
        rows.append({"#": item["id"], "item": _label(kind, item), **j["row"],
                     "ms": j["latency_ms"], "tokens": j["input_tokens"]})
    return pd.DataFrame(rows)


def render_tab() -> None:
    db = get_db()

    st.markdown("#### Judge the whole corpus")
    st.caption("A judgment is one HTTP call carrying the state and every question at once, so ten "
               "questions cost barely more than one. `judge_many` runs them over a thread pool "
               "and returns a result per item — a failure is one row, never the run.")

    top = st.columns([3, 2, 2, 3])
    with top[0]:
        name = st.selectbox("Dataset", list(DATASETS), key="batch_dataset")
    kind, qset, load, chart_cols = DATASETS[name]
    items = load(db)
    judged = store.judgments(db, kind, qset.name)
    pending = [i for i in items if i["id"] not in judged]

    with top[1]:
        count = st.number_input("How many", 1, len(items), min(25, len(items)), key="batch_n")
    with top[2]:
        only_new = st.toggle("Skip judged", value=True, key="batch_skip",
                             help="Only send items that have no stored judgment yet.")
    with top[3]:
        st.metric("stored", f"{len(judged)} / {len(items)}",
                  delta=f"{len(pending)} not yet judged" if pending else "complete",
                  delta_color="off")

    queue = (pending if only_new else items)[:int(count)]
    go = st.button(f"▶  Judge {len(queue)} item{'s' if len(queue) != 1 else ''} live",
                   type="primary", disabled=not have_key() or not queue, key="batch_go")
    if not have_key():
        st.caption("No `TYPESAFE_API_KEY` in the environment — the stored results below are still "
                   "fully browsable.")
    elif not queue:
        st.caption("Nothing queued: everything in this dataset already has a stored judgment. "
                   "Turn off **Skip judged** to re-run them.")

    if go and queue:
        _run_batch(db, kind, qset, queue)
        judged = store.judgments(db, kind, qset.name)

    st.divider()
    frame = _results_frame(kind, items, judged)
    if frame.empty:
        st.info("No stored judgments for this dataset yet.")
        return

    cols = st.columns(4)
    cols[0].metric("items judged", len(frame))
    cols[1].metric("median latency", f"{int(frame['ms'].median())} ms")
    cols[2].metric("input tokens", f"{int(frame['tokens'].sum()):,}")
    cols[3].metric("total cost",
                   f"${frame['tokens'].sum() / 1e6 * DEFAULTS['price_per_mtok']:.4f}",
                   help="input tokens only — jev bills no output")

    st.markdown("##### How the corpus broke down")
    charts = st.columns(len(chart_cols))
    for col, column in zip(charts, chart_cols):
        with col:
            st.caption(f"`{column}`")
            counts = frame[column].value_counts()
            st.bar_chart(counts, horizontal=True, height=max(140, 34 * len(counts)))

    st.markdown("##### Every judgment")
    st.caption("Sort by any column. This is the table a pipeline would write — every number here "
               "came back typed, and nothing had to be parsed out of prose.")
    st.dataframe(frame, hide_index=True, use_container_width=True, height=460,
                 column_config={"item": st.column_config.TextColumn("item", width="large"),
                                "#": st.column_config.NumberColumn(width="small")})
    st.download_button("Download as CSV", frame.to_csv(index=False).encode(),
                       file_name=f"{qset.name}-judgments.csv", mime="text/csv")


def _run_batch(db, kind: str, qset, queue: List[Dict[str, Any]]) -> None:
    """Judge `queue`, a chunk at a time, storing each chunk as it lands.

    `judge_many`'s `on_result` callback fires on the pool's worker threads, and a worker thread
    has no Streamlit script-run context — touching a progress bar from one raises
    `NoSessionContext`. So the pool runs over a chunk at a time and the bar is advanced here, on
    the main thread, between chunks. Concurrency inside a chunk is unchanged; the only cost is
    that each chunk waits for its own slowest item.
    """
    try:
        client = get_client()
    except JevError as e:
        st.error(str(e))
        return

    chunk_size = max(client.workers * 2, 8)
    progress = st.progress(0.0, text=f"0 / {len(queue)} judged")
    started = time.perf_counter()
    tokens = 0
    failures: List[str] = []
    done = 0

    for start in range(0, len(queue), chunk_size):
        chunk = queue[start:start + chunk_size]
        results = client.judge_many([(i["id"], qset.state(i)) for i in chunk], qset.questions)
        for result in results:
            if not result.ok:
                failures.append(f"#{result.key}: {result.error}")
                continue
            tokens += result.input_tokens
            store.save_judgment(db, kind, int(result.key), qset.name, result.model,
                                result.answers, qset.to_row(result.answers),
                                input_tokens=result.input_tokens, latency_ms=result.latency_ms)
        done += len(chunk)
        progress.progress(done / len(queue), text=f"{done} / {len(queue)} judged")

    elapsed = time.perf_counter() - started
    progress.empty()
    session_cost(tokens)
    ok = len(queue) - len(failures)
    st.success(f"{ok}/{len(queue)} judged in {elapsed:.1f}s "
               f"({len(queue) / elapsed:.1f} items/second over {client.workers} workers) · "
               f"{tokens:,} input tokens ≈ ${tokens / 1e6 * DEFAULTS['price_per_mtok']:.4f}")
    if failures:
        with st.expander(f"{len(failures)} item(s) failed — the rest were stored anyway"):
            for f in failures:
                st.write(f)
