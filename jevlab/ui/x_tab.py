#!/usr/bin/env python3
"""jevlab/ui/x_tab.py — 100 X posts, and the two question sets that read them.

Same table, same UI, two different judgments. A post from the markets list is judged by
`jev-x-stocks-v1` (is this a call, which way, how much weight); a post from the AI list is judged
by `jev-x-ai-v1` (what is being claimed, and what is it standing on). Neither set would say
anything useful about the other feed — which is the point of versioning a set by name.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from jevlab import db as store
from jevlab.qsets import FOR_X, x_ai, x_stocks
from jevlab.ui import render
from jevlab.ui.common import get_db, judge_panel, picker

FEEDS = {
    "stocks": ("Markets list", "a curated finance list — calls, charts, trading psychology, "
                               "and a steady drip of subscription funnels"),
    "ai": ("AI list", "an AI/tech list — model launches, benchmarks, firsthand reports, and a "
                      "great deal of opinion"),
}

BUCKETS = {
    "ticker_call": "names a ticker",
    "macro_take": "market, rates, crypto",
    "trading_lesson": "psychology and rules",
    "promo_noise": "selling something",
    "chatter": "everything else",
    "model_release": "something shipped",
    "benchmark_claim": "numbers and evals",
    "jev_typesafe": "about jev itself",
    "industry_news": "the business of AI",
    "hot_take": "opinion",
}

# Two posts that sit next to each other and should NOT score alike — the fastest way to see a
# question set discriminate rather than pattern-match.
HINTS = {
    "stocks": '<div class="jl-card"><b>Worth comparing</b><div class="jl-body" '
              'style="margin-top:.4rem;">A <i>ticker call</i> and a <i>trading lesson</i> — both '
              'sound confident; <code>post_type</code> and <code>is_actionable_call</code> pull '
              'them apart.<br>A <i>promo</i> post — <code>promotional</code> climbs and the '
              'derived <code>signal</code> collapses even when the post names a stock.<br>'
              'A post about a stock that already ran — <code>reacts_to_price_move</code> is the '
              'markets feed\'s version of the news set\'s <code>reports_price_move</code>.'
              '</div></div>',
    "ai": '<div class="jl-card"><b>Worth comparing</b><div class="jl-body" '
          'style="margin-top:.4rem;">A <i>benchmark claim</i> and a <i>hot take</i> — watch '
          '<code>evidence</code> and <code>cites_numbers</code> separate them.<br>'
          'A <i>model release</i> everyone covered vs. one nobody caught — that is what '
          '<code>novelty</code> is for.<br>Sort the Batch tab by <code>typesafe_p</code>: the '
          'feed argues about jev itself, and the noul finds those posts without a keyword list.'
          '</div></div>',
}


def _card(post: Dict[str, Any]) -> None:
    handle = post.get("author_handle") or "unknown"
    verified = " ✓" if post.get("verified") else ""
    cash = post.get("cashtags") or []
    quote = post.get("quote_text")
    st.markdown(
        f'<div class="jl-card">'
        f'<div class="jl-meta"><b>@{render.esc(handle)}</b>{verified} · '
        f'{render.esc((post.get("author_name") or ""))} · '
        f'{render.esc((post.get("posted_at_et") or "")[:16].replace("T", " "))} ET</div>'
        f'<div class="jl-body">{render.block(post["text"])}</div>'
        + (f'<div class="jl-body" style="opacity:.6;border-left:3px solid rgba(128,128,128,.3);'
           f'padding-left:.7rem;margin-top:.6rem;">quoting: {render.block(quote)}</div>'
           if quote else "")
        + f'<div class="jl-meta" style="margin-top:.7rem;">'
          f'{post.get("likes", 0):,} likes · {post.get("reposts", 0):,} reposts · '
          f'{post.get("replies", 0):,} replies · {post.get("views", 0):,} views'
        + (" · " + " ".join(f"${c}" for c in cash) if cash else "")
        + '</div></div>', unsafe_allow_html=True)


def render_tab() -> None:
    db = get_db()

    st.markdown("#### X posts  ·  `jev-x-stocks-v1` and `jev-x-ai-v1`")
    st.caption("Two feeds of the same shape, two completely different sets of questions. Switch "
               "between them and compare what each one is even asking.")

    top = st.columns([2, 2, 3, 2])
    with top[0]:
        feed = st.radio("Feed", list(FEEDS), horizontal=True,
                        format_func=lambda f: FEEDS[f][0], key="x_feed")
    qset = FOR_X[feed]
    items = store.x_posts(db, feed)
    judged = store.judgments(db, "x", qset.name)

    with top[1]:
        buckets = sorted({i["bucket"] for i in items})
        bucket = st.selectbox("Kind of post", ["all"] + buckets,
                              format_func=lambda b: f"all {len(items)} posts" if b == "all"
                              else f"{b} — {BUCKETS.get(b, '')}", key=f"x_bucket_{feed}")
    with top[2]:
        query = st.text_input("Search text and authors", key=f"x_query_{feed}",
                              placeholder="$NVDA, benchmark, @handle…")
    with top[3]:
        st.metric("judged & stored", f"{len(judged)} / {len(items)}")

    st.caption(f"**{FEEDS[feed][0]}** — {FEEDS[feed][1]}. Judged by `{qset.name}`: "
               f"{qset.describe}.")

    rows = [i for i in items if bucket in ("all", i["bucket"])]
    if query:
        q = query.lower().lstrip("@")
        rows = [i for i in rows if q in i["text"].lower()
                or q in (i["author_handle"] or "").lower()]
    if not rows:
        st.warning("No post matches that filter.")
        return

    left, right = st.columns([5, 7], gap="large")
    with left:
        table = [{"id": i["id"], "author": f"@{i['author_handle']}", "likes": i["likes"],
                  "post": " ".join((i["text"] or "").split())[:130]} for i in rows]
        chosen = picker(table, {
            "author": st.column_config.TextColumn("author", width="small"),
            "likes": st.column_config.NumberColumn("♥", width="small", format="%d"),
            "post": st.column_config.TextColumn("post", width="large")},
            key=f"x_{feed}", judged=judged)
        st.caption(f"{len(rows)} of {len(items)} posts · tick a box to select · "
                   "✓ marks a stored judgment")
        st.markdown(HINTS[feed], unsafe_allow_html=True)

    with right:
        post = store.x_post(db, chosen) if chosen else None
        if post is None:
            st.info("Pick a post on the left.")
            return
        judge_panel("x", post, qset, qset.state(post), _card)
