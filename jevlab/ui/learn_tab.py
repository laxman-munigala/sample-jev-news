#!/usr/bin/env python3
"""jevlab/ui/learn_tab.py — what jev is, the three primitives, and a playground to try them.

The playground is the part worth keeping: type any text, declare a Choice, a Score or a Noul, and
watch a typed answer come back. It is the same `JevClient.judge()` the other tabs use, with a
question set you write in the browser.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from jevlab.jev import Choice, JevError, Noul, Score
from jevlab.jev.client import DEFAULTS, have_key
from jevlab.ui import render
from jevlab.ui.common import get_client, session_cost

INTRO = """
**jev is a judgment model, not a generative one.** You hand it a *state* — some facts — and a set
of *typed questions*. It hands back calibrated numbers. It cannot write you a paragraph, and it
cannot return a value outside the type you declared.

That one constraint is what makes it useful as infrastructure. An LLM asked to classify something
returns prose you have to parse, in a shape you have to validate, at a price and a latency that
make judging ten thousand rows a project. jev returns `{"choice": "reactive", "probabilities":
{...}}` — already a number, already in range — at about **600 ms** and **$0.042 per million input
tokens**, with no output tokens billed at all.

So the division of labour in this repo, and the one worth copying:

| | does what |
|---|---|
| **jev** | the judgments: is this relevant, which way does it lean, how material is it, how true is this statement |
| **your code** | everything numeric that follows: thresholds, weights, aggregation, the final label |
| **an LLM** | only what actually needs prose — a rationale, a summary, a written brief |

Nothing in this project asks jev to do arithmetic, compare dates, or reason in several steps.
Those are its documented weaknesses, and they are also exactly what ordinary code is best at.
"""

PRIMITIVES = {
    "Choice": ("choice",
               "Pick one of N labelled options. You get the winner, a confidence, and a "
               "probability on **every** option — so 0.51/0.49 is visibly a coin flip instead of "
               "a confident-looking label.",
               """Choice(
  instructions=
    "Is this new information, or a "
    "report of a move that happened?",
  criteria={
    "new_info":
      "Discloses a fact the market "
      "did not have before.",
    "follow_up":
      "A recap of something ALREADY "
      "public.",
    "reactive":
      "It is ABOUT the price moving: "
      "'why X stock is down today'.",
  })"""),
    "Score": ("score",
              "Place the item on an **ordered rubric** you write, one description per level. The "
              "answer is a weighted position (2.7, not 3), so 'between these two levels' survives "
              "instead of being rounded away.",
              """Score(
  instructions=
    "How much should this news move "
    "the share price?",
  criteria=[
    "A listicle row, an 'other "
    "movers' mention.",
    "A single analyst note, a "
    "routine filing.",
    "A product launch, a notable "
    "contract.",
    "An earnings beat or miss, a "
    "CEO departure.",
    "M&A, an FDA decision, a fraud "
    "probe, bankruptcy.",
  ])"""),
    "Noul": ("noul",
             "How true is one statement, from 0 to 1. Use it where a boolean would lose "
             "something — most real questions are 0.83 true, not `True`.",
             """Noul(
  instructions=
    "The story reports that the "
    "price has ALREADY moved.",
  criteria={
    "true":
      "'shares are trading higher', "
      "'stock jumps 12%'.",
    "false":
      "It reports an event, even if "
      "a move may follow.",
  })"""),
}

EXAMPLES = {
    "A support ticket": (
        "Hi — I've been charged twice for the September invoice and nobody has replied to my "
        "last two emails. This is the third billing problem this year. If it isn't fixed today "
        "I'm cancelling both seats.",
        "How urgent is this ticket?",
        ["Not urgent — a question or a comment.",
         "Routine — should be handled this week.",
         "Elevated — the customer is blocked or annoyed.",
         "Urgent — money, data, or an angry customer at risk.",
         "Critical — churn or an outage is happening now."]),
    "A pull request description": (
        "Bumps the retry ceiling from 3 to 10 and drops the backoff to 50ms so the flaky "
        "integration test stops failing in CI. No other changes.",
        "What kind of change is this?",
        None),
    "A news headline": (
        "Shares of Northwind Systems jumped 14% in the pre-market after the company said it had "
        "signed a supply agreement it described as its largest ever.",
        "The text reports a price move that has already happened.",
        None),
}


def render_tab() -> None:
    st.markdown("#### What jev is")
    st.markdown(INTRO)

    st.markdown("#### The three primitives")
    st.caption("This is the entire vocabulary. Every question in this app is one of these.")
    cols = st.columns(3)
    for col, (title, (kind, blurb, code)) in zip(cols, PRIMITIVES.items()):
        with col:
            st.markdown(f'<span class="jl-chip {kind}">{title}</span>', unsafe_allow_html=True)
            st.markdown(blurb)
            st.code(code, language="python")

    st.markdown("#### How a question set is put together")
    st.caption("A `QuestionSet` is a name, the questions, how to build the state, and how to "
               "project the answers onto your own columns. The name is versioned, because stored "
               "judgments under one name must all mean the same thing — change the questions, "
               "change the name.")
    st.code('''from jevlab.jev import JevClient
from jevlab.qsets import news

item    = {...}                                  # your row
state   = news.state(item)                       # the facts jev reads — keep it tight
answers = JevClient().judge(state, news.QUESTIONS)   # ONE call, all ten questions
row     = news.to_row(answers)                   # -> your columns, ready to store

if row["timing"] == "reactive" and row["p_reactive"] > 0.8:
    skip(item)                                   # a threshold in code, on a calibrated number
''', language="python")

    st.divider()
    st.markdown("#### Playground")
    st.caption("Your own state, your own question, live. This is the same client the other tabs "
               "use.")

    example = st.selectbox("Start from", list(EXAMPLES), key="pg_example")
    default_text, default_q, default_levels = EXAMPLES[example]

    left, right = st.columns([3, 2], gap="large")
    with left:
        text = st.text_area("The state jev reads", value=default_text, height=150, key="pg_text")
        question = st.text_input("The question", value=default_q, key="pg_question")
    with right:
        kind = st.radio("Primitive", ["Choice", "Score", "Noul"],
                        index=1 if default_levels else 0, horizontal=True, key="pg_kind")
        if kind == "Choice":
            raw = st.text_area(
                "Options — one per line, as `name: what it means`", height=118, key="pg_choice",
                value="bugfix: fixes incorrect behaviour\n"
                      "config_tweak: only changes a constant or a setting\n"
                      "feature: adds new behaviour\n"
                      "refactor: changes structure, not behaviour")
        elif kind == "Score":
            raw = st.text_area("Rubric — one level per line, lowest first", height=118,
                               key="pg_score",
                               value="\n".join(default_levels or [
                                   "Not at all.", "Slightly.", "Moderately.", "Strongly.",
                                   "Completely."]))
        else:
            raw = st.text_area("What `true` and `false` mean — two lines", height=118,
                               key="pg_noul",
                               value="true: the text states a move that has already happened\n"
                                     "false: it looks forward, or is not about price")

    if st.button("▶  Ask jev", type="primary", disabled=not have_key(), key="pg_go"):
        _run_playground(text, question, kind, raw)
    if not have_key():
        st.caption("The playground needs `TYPESAFE_API_KEY` in the environment.")

    st.divider()
    with st.expander("Where everything lives in this repo"):
        st.markdown("""
| path | what is in it |
|---|---|
| `jevlab/jev/client.py` | credentials, one call per judgment, the thread pool, cost accounting |
| `jevlab/jev/questions.py` | the `QuestionSet` type: name, questions, `state()`, `to_row()` |
| `jevlab/qsets/news.py` | **`jev-news-v1`** — edit the news classifiers here |
| `jevlab/qsets/x_stocks.py` | **`jev-x-stocks-v1`** — the markets feed |
| `jevlab/qsets/x_ai.py` | **`jev-x-ai-v1`** — the AI feed |
| `jevlab/db.py` | the three tables, and the judgment cache |
| `scripts/precompute.py` | the pass that filled the shipped judgments |
| `docs/NEWS.md`, `docs/X_POSTS.md` | every question, and what it is for |
""")


def _parse(kind: str, raw: str) -> Any:
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if kind == "Score":
        return list(lines)
    criteria: Dict[str, str] = {}
    for line in lines:
        name, _, meaning = line.partition(":")
        criteria[name.strip()] = meaning.strip() or name.strip()
    return criteria


def _run_playground(text: str, question: str, kind: str, raw: str) -> None:
    criteria = _parse(kind, raw)
    if not criteria:
        st.warning("Give the question at least one option or level.")
        return
    try:
        q = {"Choice": Choice, "Score": Score, "Noul": Noul}[kind](
            instructions=question, criteria=criteria)
    except Exception as e:                        # noqa: BLE001 — a malformed question is normal
        st.error(f"That question does not type-check: {e}")
        return

    try:
        client = get_client()
        with st.spinner("judging…"):
            answers = client.judge({"text": text}, {"answer": q})
    except JevError as e:
        st.error(str(e))
        return

    session_cost(0)
    answer = answers["answer"]
    st.write("")
    if kind == "Choice":
        render.choice_answer("answer", q, answer)
    elif kind == "Score":
        render.score_answer("answer", q, answer)
    else:
        st.markdown(f'<span class="jl-chip noul">Noul</span>'
                    f'<div class="jl-verdict">{float(answer.get("noul") or 0):.2f}</div>'
                    f'<div class="jl-sub">0 = false · 1 = true</div>', unsafe_allow_html=True)
        st.progress(float(answer.get("noul") or 0))
    with st.expander("The raw answer"):
        st.json(answer)
