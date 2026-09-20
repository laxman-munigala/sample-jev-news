"""jevlab.jev — a small, self-contained wrapper around the TypeSafe `jev` judgment model.

`jev` is not a chatbot. You hand it a **state** (some facts) and a set of **typed questions**, and
it hands back calibrated numbers — a probability per option, a weighted position on a rubric, a
0-1 likelihood. It cannot write prose, and it cannot return a value outside the type you declared.
That is the whole point: the answer is already a number your code can threshold, so nothing has to
parse a paragraph and hope.

Three primitives, and they are the entire vocabulary:

    Choice   pick one of N labelled options  -> {"choice": "reactive", "probabilities": {...}}
    Score    place it on an ordered rubric   -> {"score": 2.7}   (0 .. len(criteria)-1)
    Noul     how true is this statement      -> {"noul": 0.83}   (0 .. 1)

Two objects here:

    JevClient    credentials, one HTTP call per judgment, a thread pool for many, cost accounting
    QuestionSet  a NAMED, VERSIONED bundle of questions + how to build the state + how to project
                 the answers onto your own columns

Usage is three lines:

    from jevlab.jev import JevClient
    from jevlab.qsets import news
    answers = JevClient().judge(news.state(item), news.QUESTIONS)

This is a trimmed copy of a production module: credentials come from the environment only, and the
domain logic lives in `jevlab/qsets/`. Nothing in here knows what news or an X post is.
"""

from __future__ import annotations

from jevlab.jev.client import DEFAULTS, JevClient, JevError, Judgment, resolve_key, truncate
from jevlab.jev.questions import Choice, Noul, QuestionSet, Score

__all__ = ["JevClient", "JevError", "Judgment", "QuestionSet", "Choice", "Noul", "Score",
           "DEFAULTS", "resolve_key", "truncate"]
