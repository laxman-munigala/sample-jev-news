#!/usr/bin/env python3
"""jevlab/qsets/x_stocks.py — `jev-x-stocks-v1`: reading a finance X feed.

The problem this set exists for: a curated markets list is maybe 15% signal. The rest is trading
psychology, motivational posting, chart porn with no thesis, and subscription funnels. A keyword
filter cannot tell "$AMD weekly closing at all-time highs" (an observation) from "$EOSE selected
by the U.S. Army for a new depot contract" (a fact) from "What is your excuse losers? Go get it
done!" (nothing). All three carry a cashtag or a confident tone.

So the set is built around **separating the post's kind from its direction**, and only then asking
how much weight it deserves.

| question | type | what it is for |
|---|---|---|
| `post_type` | choice | the noise filter: a call, analysis, commentary, a lesson, a pitch, chatter |
| `subject` | choice | a single stock, a sector, the whole market, crypto, or nothing tradeable |
| `stance` | choice | `p(bullish) − p(bearish)` on whatever the post is about |
| `horizon` | choice | intraday / weeks / long term — a day-trade tweet is not a thesis |
| `conviction` | score | hedged musing vs "I am buying this here" |
| `evidence` | score | asserted, a chart, numbers, or a primary source |
| `promotional` | score | how much the post is selling something |
| `is_actionable_call` | noul | could a reader act on this without asking a question? |
| `discloses_position` | noul | the author says they own it / are in the trade |
| `reacts_to_price_move` | noul | the X analogue of news `reports_price_move` |

Compare with `jev-news-v1`: `stance` and `direction` ask the same thing of different objects, and
`reacts_to_price_move` mirrors `reports_price_move` exactly. That is on purpose — it shows how a
question set is ported to a new domain rather than reinvented.
"""

from __future__ import annotations

from typing import Any, Dict

from jevlab.jev import Choice, Noul, QuestionSet, Score, truncate

NAME = "jev-x-stocks-v1"

QUESTIONS: Dict[str, Any] = {
    "post_type": Choice(
        instructions="What kind of post is this, for someone scanning a markets feed for things "
                     "worth acting on?",
        criteria={
            "trade_call": "A specific position or trade: buying, selling, adding, trimming, a "
                          "level to watch, an entry or a target.",
            "analysis": "A thesis or read on a company or asset: what it is worth, why it moves, "
                        "what the chart or the numbers say.",
            "news_relay": "Relaying a fact that happened: a contract, a filing, a launch, a "
                          "print, a headline, an earnings number.",
            "market_commentary": "A read on the market, a sector, rates, flows or breadth rather "
                                 "than one name.",
            "education": "A lesson, a rule, trading psychology, a general principle. No position "
                         "and no current claim.",
            "promotion": "Selling something: a subscription, a newsletter, a course, a Discord, "
                         "a referral code, 'link in bio'.",
            "chatter": "Small talk, a joke, a reply fragment, a photo, an opinion about someone. "
                       "Nothing about an asset.",
        }),
    "subject": Choice(
        instructions="What is the post actually about?",
        criteria={
            "single_stock": "One company, named or cashtagged.",
            "several_stocks": "A basket, a screen, a watchlist, or a comparison of several names.",
            "sector_or_theme": "A sector, an industry or a theme (AI, energy, small caps, "
                               "software).",
            "whole_market": "Indices, the tape, the Fed, rates, macro, breadth.",
            "crypto": "Bitcoin, a token, or crypto as an asset class.",
            "not_markets": "Nothing tradeable: the author's life, a meme, a general observation.",
        }),
    "stance": Choice(
        instructions="Which way does the post lean on whatever it is about? If it is about "
                     "nothing tradeable, that is neutral.",
        criteria={
            "bullish": "It reads as positive: expects it to go up, likes it here, is long, sees "
                       "strength.",
            "bearish": "It reads as negative: expects it to go down, is short, sees weakness, is "
                       "warning.",
            "neutral": "No direction taken, both sides, purely descriptive, or not about an "
                       "asset at all.",
        }),
    "horizon": Choice(
        instructions="Over what time frame would the post's view play out?",
        criteria={
            "intraday": "Today's session: the open, a level right now, a scalp.",
            "swing": "Days to a few weeks: a setup, a weekly chart, an earnings run.",
            "long_term": "Months to years: a thesis, a hold, a compounding argument.",
            "none": "No time frame — the post makes no claim that plays out.",
        }),
    "conviction": Score(
        instructions="How strongly is the view held, as written? Judge the commitment in the "
                     "wording, not whether the view is correct.",
        criteria=[
            "No view at all.",
            "A musing or a question: 'interesting here', 'watching this', 'thoughts?'.",
            "A leaning, hedged: 'looks constructive', 'could work if…'.",
            "A clear view stated plainly: 'this is going higher', 'I like this setup'.",
            "Emphatic and committed: sized, repeated, 'my largest position', 'back up the truck'.",
        ]),
    "evidence": Score(
        instructions="What is the claim standing on?",
        criteria=[
            "Nothing — assertion, vibes, or no claim to support.",
            "An appeal to the author's own experience or track record.",
            "A chart, a level, or a technical pattern.",
            "Specific numbers: revenue, margins, a valuation, a growth rate, a flow.",
            "A primary source quoted or linked: a filing, a release, an official announcement.",
        ]),
    "promotional": Score(
        instructions="How much is this post selling something — the author's service, their "
                     "track record, or a position they need others to buy?",
        criteria=[
            "Not selling anything.",
            "A soft mention of their own work in passing.",
            "A clear plug alongside real content.",
            "Mostly a pitch with a thin wrapper of content.",
            "Pure funnel: a link, a code, 'join', 'DM me', nothing else.",
        ]),
    "is_actionable_call": Noul(
        instructions="A reader could act on this post without asking the author a follow-up "
                     "question: it names what, which way, and roughly when.",
        criteria={"true": "The asset, the direction and the timing are all recoverable from the "
                          "post itself.",
                  "false": "Something essential is missing, or there is no call at all."}),
    "discloses_position": Noul(
        instructions="The author says they personally hold, are entering, or are exiting the "
                     "position.",
        criteria={"true": "'I'm long', 'added today', 'sold my last third', a portfolio update.",
                  "false": "No statement about the author's own book."}),
    "reacts_to_price_move": Noul(
        instructions="The post is about a price move that has ALREADY happened, rather than one "
                     "the author expects.",
        criteria={"true": "'Closing at all-time highs', 'up 12% today', 'nice lift', a recap of "
                          "the session.",
                  "false": "It looks forward, or it is not about price at all."}),
}


def state(post: Dict[str, Any], *, text_chars: int = 900) -> Dict[str, Any]:
    """The facts one judgment reads. Engagement is included because it is part of how a reader
    weighs a post — but the questions never ask jev to do arithmetic on it."""
    return {
        "author": f"@{post.get('author_handle') or 'unknown'}"
                  + (f" ({post['author_name']})" if post.get("author_name") else "")
                  + (" · verified" if post.get("verified") else ""),
        "posted": post.get("posted_at_et") or "",
        "text": truncate(post.get("text"), text_chars),
        "quoted_post": truncate(post.get("quote_text"), 400) or None,
        "cashtags": list(post.get("cashtags") or []),
        "engagement": {"likes": post.get("likes", 0), "reposts": post.get("reposts", 0),
                       "replies": post.get("replies", 0), "views": post.get("views", 0)},
    }


def to_row(answers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ch = lambda q: (answers.get(q) or {}).get("choice")                      # noqa: E731
    pr = lambda q: (answers.get(q) or {}).get("probabilities") or {}         # noqa: E731
    cf = lambda q: (answers.get(q) or {}).get("confidence")                  # noqa: E731
    sc = lambda q: (answers.get(q) or {}).get("score")                       # noqa: E731
    nl = lambda q: (answers.get(q) or {}).get("noul")                        # noqa: E731

    p_bull, p_bear = pr("stance").get("bullish"), pr("stance").get("bearish")
    net = None if p_bull is None or p_bear is None else p_bull - p_bear
    conviction, evidence = sc("conviction"), sc("evidence")
    promo = sc("promotional")

    # The one number a feed reader actually wants: is this worth a second look? Code, not jev —
    # jev supplied the four calibrated inputs, the weighting is a decision we can test and tune.
    signal = None
    if None not in (conviction, evidence, promo):
        signal = round(max(0.0, min(10.0,
            (conviction / 4 * 4.0) + (evidence / 4 * 4.0) + (nl("is_actionable_call") or 0) * 2.0
            - (promo / 4 * 3.0))), 2)

    return {
        "post_type": ch("post_type"), "subject": ch("subject"), "stance": ch("stance"),
        "horizon": ch("horizon"),
        "signal": signal,
        "p_bull": p_bull, "p_bear": p_bear, "p_neutral": pr("stance").get("neutral"),
        "net_p": net,
        "p_trade_call": pr("post_type").get("trade_call"),
        "p_promotion": pr("post_type").get("promotion"),
        "p_chatter": pr("post_type").get("chatter"),
        "conf_post_type": cf("post_type"), "conf_stance": cf("stance"),
        "conviction": conviction, "evidence": evidence, "promotional": promo,
        "actionable_p": nl("is_actionable_call"),
        "discloses_position_p": nl("discloses_position"),
        "reacts_to_move_p": nl("reacts_to_price_move"),
    }


SET = QuestionSet(
    name=NAME, questions=QUESTIONS, state=state, to_row=to_row,
    title="X — markets feed",
    describe="per post: kind, subject, stance, horizon, conviction, evidence, promotional tone, "
             "and three true/false likelihoods",
    columns=tuple(to_row({}).keys()))
