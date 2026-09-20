#!/usr/bin/env python3
"""jevlab/ui/news_tab.py — 100 market news stories, judged by `jev-news-v1`.

The story list is deliberately mixed: a twelve-ticker movers roundup sits next to an earnings
release, a transcript next to an unconfirmed "reportedly". Pick two neighbours and watch `timing`
and `relevance` swing — that contrast is the whole demonstration.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from jevlab import db as store
from jevlab.qsets import news
from jevlab.ui import render
from jevlab.ui.common import get_db, judge_panel, picker

BUCKETS = {
    "price_move": "reports a move that already happened",
    "roundup": "a list of many tickers",
    "transcript": "an earnings call transcript",
    "earnings": "results and quarters",
    "analyst": "ratings and price targets",
    "m_and_a": "deals and stakes",
    "speculation": "unconfirmed, 'reportedly'",
    "regulatory_legal": "regulators, courts, agencies",
    "product_contract": "launches, wins, partnerships",
    "guidance_capital": "outlook, raises, buybacks",
    "leadership": "executives and boards",
    "macro_other": "rates, commodities, everything else",
}


def _card(item: Dict[str, Any]) -> None:
    others = item["other_tickers"]
    tags = (f" · also tagged {len(others)} other ticker" + ("s" if len(others) != 1 else "")
            if others else " · the only ticker tagged")
    body = (item.get("body") or "")[:700]
    st.markdown(
        f'<div class="jl-card">'
        f'<h4>{render.esc(item["headline"])}</h4>'
        f'<div class="jl-meta">{render.esc(item["published_et"][:16].replace("T", " "))} ET · '
        f'{render.esc(item["source"])} · judged for '
        f'<b>{render.esc(item["subject_ticker"])} — {render.esc(item["subject_name"])}</b>'
        f'{render.esc(tags)}</div>'
        f'<div class="jl-body">{render.block(body)}…</div></div>', unsafe_allow_html=True)
    if others:
        st.caption("Other tickers on the wire: " + ", ".join(others[:20])
                   + (" …" if len(others) > 20 else ""))


def render_tab() -> None:
    db = get_db()
    items = store.news_items(db)
    judged = store.judgments(db, "news", news.NAME)

    st.markdown("#### Market news  ·  `jev-news-v1`")
    st.caption("Ten questions per story, one call. The one that matters: **is this new "
               "information, or is it telling me the stock already moved?** Benzinga publishes "
               "both all day and they read almost identically.")

    top = st.columns([2, 3, 2])
    with top[0]:
        bucket = st.selectbox("Kind of story", ["all"] + list(BUCKETS),
                              format_func=lambda b: "all 100 stories" if b == "all"
                              else f"{b} — {BUCKETS[b]}", key="news_bucket")
    with top[1]:
        query = st.text_input("Search headlines and tickers", key="news_query",
                              placeholder="earnings, NVDA, lawsuit…")
    with top[2]:
        st.metric("judged & stored", f"{len(judged)} / {len(items)}")

    rows = [i for i in items if bucket in ("all", i["bucket"])]
    if query:
        q = query.lower()
        rows = [i for i in rows
                if q in i["headline"].lower() or q in i["subject_ticker"].lower()
                or q in (i["subject_name"] or "").lower()]
    if not rows:
        st.warning("No story matches that filter.")
        return

    left, right = st.columns([5, 7], gap="large")
    with left:
        table = [{"id": i["id"], "ticker": i["subject_ticker"], "headline": i["headline"]}
                 for i in rows]
        chosen = picker(table, {
            "ticker": st.column_config.TextColumn("ticker", width="small"),
            "headline": st.column_config.TextColumn("headline", width="large")},
            key="news", judged=judged)
        st.caption(f"{len(rows)} of {len(items)} stories · tick a box to select · "
                   "✓ marks a stored judgment")
        st.markdown(
            '<div class="jl-card"><b>Worth comparing</b>'
            '<div class="jl-body" style="margin-top:.4rem;">'
            'A <i>price move</i> story and a <i>product/contract</i> story — watch '
            '<code>timing</code> go from <b>reactive</b> to <b>new_info</b>.<br>'
            'A <i>roundup</i> and a single-company release — watch <code>relevance</code> fall '
            'from <b>primary</b> to <b>irrelevant</b> while the wire tagged both the same way.'
            '<br>A <i>speculation</i> story — <code>is_speculation</code> and '
            '<code>first_disclosure</code> pull in opposite directions.</div></div>',
            unsafe_allow_html=True)

    with right:
        item = store.news_item(db, chosen) if chosen else None
        if item is None:
            st.info("Pick a story on the left.")
            return
        judge_panel("news", item, news.SET, news.state(item), _card)
