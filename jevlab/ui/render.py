#!/usr/bin/env python3
"""jevlab/ui/render.py — how a typed answer is drawn, and the small shared UI pieces.

Everything jev returns is one of three shapes, so everything here is one of three renderers:

    choice -> the picked option, its confidence, and a bar per option (they sum to 1)
    score  -> a position on the rubric, with the level descriptions it sits between
    noul   -> a single 0-1 likelihood

Keeping the drawing in one module is what lets the News tab and both X tabs show three completely
different question sets with the same code.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import pandas as pd
import streamlit as st

TYPE_LABEL = {"choice": "Choice", "score": "Score", "noul": "Noul"}
TYPE_HELP = {
    "choice": "one of N options, with a probability on each",
    "score": "a weighted position on an ordered rubric",
    "noul": "how true a statement is, 0 to 1",
}

CSS = """
<style>
  /* Streamlit caps even its wide layout at 1400px, which wastes half of a large monitor and
     squeezes the story list. `min()` widens it where there is room and gets out of the way on a
     laptop. !important because Streamlit's own rule is more specific than a class selector. */
  .stMainBlockContainer, .block-container {
      max-width: min(1860px, 97%) !important; padding: 2.2rem 2.2rem 4rem 2.2rem !important;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .jl-card {border: 1px solid rgba(128,128,128,.22); border-radius: 12px;
            padding: 1rem 1.15rem; margin-bottom: .85rem; background: rgba(128,128,128,.045);}
  .jl-card h4 {margin: 0 0 .45rem 0; font-size: 1.06rem; line-height: 1.4;}
  .jl-meta {font-size: .78rem; opacity: .68; margin-bottom: .5rem;}
  .jl-body {font-size: .88rem; line-height: 1.55; opacity: .92;}
  .jl-chip {display: inline-block; padding: .1rem .5rem; margin: 0 .3rem .3rem 0;
            border-radius: 999px; font-size: .72rem; font-weight: 600;
            border: 1px solid rgba(128,128,128,.3); opacity: .85;}
  .jl-chip.choice {background: rgba(59,130,246,.14);}
  .jl-chip.score  {background: rgba(168,85,247,.14);}
  .jl-chip.noul   {background: rgba(16,185,129,.14);}
  .jl-q {font-size: .86rem; margin: .1rem 0 .35rem 0;}
  .jl-opts {font-size: .78rem; opacity: .7; margin: 0 0 .7rem 0;}
  .jl-verdict {font-size: 1.5rem; font-weight: 650; line-height: 1.15; margin: .1rem 0 .2rem 0;}
  .jl-sub {font-size: .76rem; opacity: .65;}
  div[data-testid="stMetricValue"] {font-size: 1.45rem;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(text: Any) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def block(text: Any) -> str:
    """Escaped text safe to place inside an HTML card.

    Streamlit parses markdown BEFORE the raw HTML, so a newline inside a `<div>` ends the HTML
    block and the rest of the card is printed as literal markup — and an X post is mostly
    newlines. Turning them into `<br>` keeps the whole card on one line as far as the parser is
    concerned."""
    return esc(text).replace("\r\n", "\n").replace("\n", "<br>")


# ───────────────────────────────────────────────────── question preview

def question_preview(questions: Mapping[str, Any]) -> None:
    """What jev is about to be asked, before anything is called. Options and rubric levels are
    shown in full, because they ARE the classifier — there is no prompt hiding behind them."""
    for qid, q in questions.items():
        kind = getattr(q, "type", "?")
        st.markdown(
            f'<span class="jl-chip {kind}">{TYPE_LABEL.get(kind, kind)}</span>'
            f'<code>{esc(qid)}</code>'
            f'<div class="jl-q">{esc(getattr(q, "instructions", ""))}</div>',
            unsafe_allow_html=True)
        criteria = getattr(q, "criteria", None)
        if isinstance(criteria, Mapping):
            opts = " · ".join(f"<b>{esc(k)}</b>" for k in criteria)
        elif criteria is not None:
            opts = " → ".join(f"<b>{i}</b>" for i in range(len(criteria)))
        else:
            opts = ""
        st.markdown(f'<div class="jl-opts">{opts}</div>', unsafe_allow_html=True)


def question_table(questions: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for qid, q in questions.items():
        kind = getattr(q, "type", "?")
        criteria = getattr(q, "criteria", None)
        if isinstance(criteria, Mapping):
            options = ", ".join(criteria)
        elif criteria is not None:
            options = f"0–{len(criteria) - 1} (rubric)"
        else:
            options = "0–1"
        rows.append({"question": qid, "type": TYPE_LABEL.get(kind, kind),
                     "asks": getattr(q, "instructions", ""), "answer space": options})
    return pd.DataFrame(rows)


# ───────────────────────────────────────────────────────── answers

def _prob_frame(probabilities: Mapping[str, float]) -> pd.DataFrame:
    return (pd.DataFrame({"option": list(probabilities), "p": list(probabilities.values())})
            .sort_values("p", ascending=False).reset_index(drop=True))


def _prob_table(probabilities: Mapping[str, float], height: Optional[int] = None) -> None:
    st.dataframe(
        _prob_frame(probabilities), hide_index=True, use_container_width=True, height=height,
        column_config={
            "option": st.column_config.TextColumn("option", width="medium"),
            "p": st.column_config.ProgressColumn("probability", min_value=0.0, max_value=1.0,
                                                 format="%.2f", width="medium")})


def choice_answer(qid: str, question: Any, answer: Dict[str, Any]) -> None:
    probs = answer.get("probabilities") or {}
    st.markdown(
        f'<span class="jl-chip choice">Choice</span><code>{esc(qid)}</code>'
        f'<div class="jl-verdict">{esc(answer.get("choice"))}</div>'
        f'<div class="jl-sub">confidence {answer.get("confidence", 0):.2f} · '
        f'{len(probs)} options</div>', unsafe_allow_html=True)
    if probs:
        _prob_table(probs, height=min(38 * len(probs) + 38, 260))


def score_answer(qid: str, question: Any, answer: Dict[str, Any]) -> None:
    levels = list(getattr(question, "criteria", []) or [])
    top = max(0, len(levels) - 1)
    value = float(answer.get("score") or 0.0)
    legend = answer.get("legend") or {str(i): t for i, t in enumerate(levels)}
    nearest = legend.get(str(int(round(value))), "")
    st.markdown(
        f'<span class="jl-chip score">Score</span><code>{esc(qid)}</code>'
        f'<div class="jl-verdict">{value:.2f} <span class="jl-sub">/ {top}</span></div>'
        f'<div class="jl-sub">confidence {answer.get("confidence", 0):.2f} · '
        f'nearest level: {esc(nearest)}</div>', unsafe_allow_html=True)
    st.progress(min(1.0, value / top) if top else 0.0)
    probs = answer.get("probabilities") or {}
    if probs:
        frame = pd.DataFrame({
            "level": [f"{k} · {str(legend.get(k, ''))[:52]}…" for k in probs],
            "p": list(probs.values())})
        st.dataframe(frame, hide_index=True, use_container_width=True,
                     height=min(38 * len(frame) + 38, 260),
                     column_config={
                         "level": st.column_config.TextColumn("level", width="medium"),
                         "p": st.column_config.ProgressColumn(
                             "probability", min_value=0.0, max_value=1.0, format="%.2f")})


def noul_table(qids, questions: Mapping[str, Any], answers: Mapping[str, Any]) -> None:
    rows = []
    for qid in qids:
        a = answers.get(qid) or {}
        rows.append({"statement": getattr(questions[qid], "instructions", qid),
                     "question": qid, "likelihood": float(a.get("noul") or 0.0)})
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, use_container_width=True,
        column_config={
            "statement": st.column_config.TextColumn("statement jev weighed", width="large"),
            "question": st.column_config.TextColumn("id", width="small"),
            "likelihood": st.column_config.ProgressColumn(
                "how true (0–1)", min_value=0.0, max_value=1.0, format="%.2f", width="medium")})


def answers_block(questions: Mapping[str, Any], answers: Mapping[str, Any]) -> None:
    """Every answer in a set, grouped by primitive: choices, then scores, then the nouls."""
    kinds = {qid: getattr(q, "type", "?") for qid, q in questions.items()}
    choices = [q for q, k in kinds.items() if k == "choice" and q in answers]
    scores = [q for q, k in kinds.items() if k == "score" and q in answers]
    nouls = [q for q, k in kinds.items() if k == "noul" and q in answers]

    if choices:
        st.markdown("##### Choices &nbsp;<span class='jl-sub'>one option wins; the rest keep "
                    "their probability</span>", unsafe_allow_html=True)
        for i in range(0, len(choices), 2):
            for col, qid in zip(st.columns(2), choices[i:i + 2]):
                with col:
                    choice_answer(qid, questions[qid], answers[qid])
    if scores:
        st.markdown("##### Scores &nbsp;<span class='jl-sub'>a weighted position on an ordered "
                    "rubric, not a rounded pick</span>", unsafe_allow_html=True)
        for i in range(0, len(scores), 2):
            for col, qid in zip(st.columns(2), scores[i:i + 2]):
                with col:
                    score_answer(qid, questions[qid], answers[qid])
    if nouls:
        st.markdown("##### Nouls &nbsp;<span class='jl-sub'>how true each statement is, 0 to 1"
                    "</span>", unsafe_allow_html=True)
        noul_table(nouls, questions, answers)


def derived_row(row: Mapping[str, Any]) -> None:
    """`to_row()` — the columns the application actually stores. Code's work, not jev's."""
    frame = pd.DataFrame({"column": list(row), "value": [
        "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
        for v in row.values()]})
    st.dataframe(frame, hide_index=True, use_container_width=True, height=360,
                 column_config={"column": st.column_config.TextColumn(width="medium")})


def run_meta(source: str, model: str, latency_ms: int, tokens: int,
             price_per_mtok: float = 0.042) -> None:
    cost = tokens / 1_000_000 * price_per_mtok
    cols = st.columns(4)
    cols[0].metric("source", source)
    cols[1].metric("model", model or "—")
    cols[2].metric("latency", f"{latency_ms} ms" if latency_ms else "—")
    cols[3].metric("cost", f"${cost:.5f}", help=f"{tokens:,} input tokens at "
                                                f"${price_per_mtok}/M · jev bills no output")
