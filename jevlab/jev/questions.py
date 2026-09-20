#!/usr/bin/env python3
"""jevlab/jev/questions.py — the `QuestionSet`: a named, versioned bundle of typed questions.

A domain declares one of these and hands it to `JevClient`. It owns three things and nothing else:

    name        what the stored judgments are keyed by — **CHANGE THE QUESTIONS, CHANGE THE NAME.**
                Rows saved under `jev-news-v1` must all mean the same thing, or comparing two runs
                compares nothing. This is the same discipline you would apply to a prompt version.
    state(...)  your object -> the facts jev judges. Keep it TIGHT: jev's documented failure mode
                is a large state stuffed with context the questions never use.
    to_row(...) the raw answers -> a flat dict of your own columns, so storage stays your business
                and this module never learns what a news story is.

`Choice`, `Score` and `Noul` are re-exported from the SDK so a question set can declare questions
without importing the SDK directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Tuple

from typesafe_sdk import Choice, Noul, Score

__all__ = ["QuestionSet", "Choice", "Noul", "Score"]


@dataclass(frozen=True)
class QuestionSet:
    """A named bundle of questions plus the two adapters around it."""

    name: str
    questions: Mapping[str, Any]
    state: Callable[..., Any]
    to_row: Callable[[Dict[str, Any]], Dict[str, Any]]
    title: str = ""
    describe: str = ""
    columns: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name or not self.questions:
            raise ValueError("a QuestionSet needs a name and at least one question")

    def kinds(self) -> Dict[str, str]:
        """{question_id: 'choice' | 'score' | 'noul'} — what the UI needs to render each answer."""
        return {qid: getattr(q, "type", "?") for qid, q in self.questions.items()}
