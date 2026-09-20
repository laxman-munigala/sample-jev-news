"""jevlab.qsets — the three question sets this demo ships, and the registry the UI reads.

A question set is the only domain-specific thing in the project. `jevlab/jev/` knows nothing about
news or X; each module here declares its own questions, its own state builder, and its own
projection onto columns.

    jev-news-v1      news.SET       market news, per (story, company)
    jev-x-stocks-v1  x_stocks.SET   a finance X feed, per post
    jev-x-ai-v1      x_ai.SET       an AI/tech X feed, per post

The two X sets read the same kind of object and share not one question. That is the lesson: the
set encodes what *this* reader wants to know, and it is versioned by name so the answers stored
under it always mean the same thing.
"""

from __future__ import annotations

from typing import Dict

from jevlab.jev import QuestionSet
from jevlab.qsets import news, x_ai, x_stocks

SETS: Dict[str, QuestionSet] = {s.name: s for s in (news.SET, x_stocks.SET, x_ai.SET)}

# Which set judges which kind of row in `data/sample.db`.
FOR_NEWS = news.SET
FOR_X = {"stocks": x_stocks.SET, "ai": x_ai.SET}

__all__ = ["SETS", "FOR_NEWS", "FOR_X", "news", "x_stocks", "x_ai"]
