#!/usr/bin/env python3
"""jevlab/ui/common.py — the pieces the News tab and the X tab share.

Both tabs do the same four things: pick an item, show the state jev will read, show the questions
it will be asked, and then either show the cached judgment or make a live call and store it. The
only difference between them is which question set and which table. So all of it lives here, and
a tab is a dozen lines of layout.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

import pandas as pd
import streamlit as st

from jevlab import db as store
from jevlab.jev import JevClient, JevError, QuestionSet
from jevlab.jev.client import have_key
from jevlab.ui import render


@st.cache_resource(show_spinner=False)
def get_client() -> JevClient:
    """One client for the whole session. It is thread-safe and holds no per-item state."""
    return JevClient()


@st.cache_resource(show_spinner=False)
def get_db():
    return store.connect()


def session_cost(tokens: int = 0) -> Dict[str, Any]:
    """Running total of what this browser session has spent on live calls."""
    totals = st.session_state.setdefault("spend", {"calls": 0, "tokens": 0})
    if tokens:
        totals["calls"] += 1
        totals["tokens"] += tokens
    return totals


def run_live(kind: str, item_id: int, qset: QuestionSet, state: Any) -> Optional[Dict[str, Any]]:
    """One live judgment, stored in the database. Returns the cached-shape dict, or None on
    failure (the error is shown in place)."""
    try:
        client = get_client()
    except JevError as e:
        st.error(str(e))
        return None
    with st.spinner(f"asking jev {len(qset.questions)} questions…"):
        judgment = client.judge_one(item_id, state, qset.questions)
    if not judgment.ok:
        st.error(judgment.error)
        return None
    row = qset.to_row(judgment.answers)
    db = get_db()
    store.save_judgment(db, kind, item_id, qset.name, judgment.model, judgment.answers, row,
                        input_tokens=judgment.input_tokens, latency_ms=judgment.latency_ms)
    session_cost(judgment.input_tokens)
    return store.judgment(db, kind, item_id, qset.name, judgment.model)


def picker(rows: List[Dict[str, Any]], columns: Dict[str, Any], key: str,
           judged: Optional[Mapping[int, Any]] = None) -> Optional[int]:
    """A compact selectable table. Returns the chosen item's id."""
    frame = pd.DataFrame(rows)
    frame.insert(0, "judged", ["✓" if (judged or {}).get(i) else "" for i in frame["id"]])
    state_key = f"{key}_selected"
    event = st.dataframe(
        frame, hide_index=True, use_container_width=True, height=430,
        on_select="rerun", selection_mode="single-row", key=f"{key}_table",
        column_config={"judged": st.column_config.TextColumn("✓", width="small",
                                                             help="a stored judgment exists"),
                       "id": st.column_config.NumberColumn("#", width="small"), **columns})
    picked = event.selection.rows if event and event.selection else []
    if picked:
        st.session_state[state_key] = int(frame.iloc[picked[0]]["id"])
    return st.session_state.get(state_key) or (int(frame.iloc[0]["id"]) if len(frame) else None)


def judge_panel(kind: str, item: Dict[str, Any], qset: QuestionSet, state: Any,
                card: Callable[[Dict[str, Any]], None]) -> None:
    """The right-hand pane: the item, what will be asked, the button, and the answers."""
    db = get_db()
    cached = store.judgment(db, kind, item["id"], qset.name)

    card(item)

    with st.expander("The state jev reads  ·  the facts, and nothing else", expanded=False):
        st.caption("A judgment gets exactly this. No prompt, no examples, no instructions beyond "
                   "the questions themselves — and deliberately no filler: a bloated state is "
                   "jev's documented failure mode.")
        st.json(state, expanded=True)

    with st.expander(f"The {len(qset.questions)} questions  ·  `{qset.name}`", expanded=False):
        st.caption(f"{qset.describe}. Every option below is part of the type — jev cannot answer "
                   "outside it.")
        render.question_preview(qset.questions)

    left, right = st.columns([2, 3])
    with left:
        label = "Re-run jev live" if cached else "Run jev"
        clicked = st.button(f"▶  {label}", type="primary", use_container_width=True,
                            disabled=not have_key(), key=f"run_{kind}_{item['id']}")
    with right:
        if not have_key():
            st.caption("No `TYPESAFE_API_KEY` in the environment — showing the stored judgment. "
                       "Set the key and restart to make live calls.")
        elif cached:
            st.caption(f"A stored judgment from **{cached['model']}** is shown below. "
                       "Re-running replaces it.")

    if clicked:
        fresh = run_live(kind, item["id"], qset, state)
        if fresh:
            cached = fresh

    st.divider()
    if not cached:
        st.info("No judgment stored for this item yet — press **Run jev**.")
        return

    render.run_meta("live · just now" if clicked else "stored",
                    cached["model"], cached["latency_ms"], cached["input_tokens"])
    st.write("")
    render.answers_block(qset.questions, cached["answers"])

    with st.expander("What the application stores  ·  `to_row()`", expanded=False):
        st.caption("jev returned the calibrated numbers. Everything here — the thresholds, the "
                   "1–10 rescaling, the composite scores — is ordinary Python in "
                   f"`jevlab/qsets/`, where it can be read and tested.")
        render.derived_row(cached["row"])

    with st.expander("Raw answers  ·  exactly what the API returned", expanded=False):
        st.json(cached["answers"], expanded=False)
