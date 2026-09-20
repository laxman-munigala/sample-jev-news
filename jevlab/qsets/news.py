#!/usr/bin/env python3
"""jevlab/qsets/news.py — `jev-news-v1`: what a markets reader judges about a news story.

Ten questions, one call, asked per **(story, company)** pair. The interesting property of this set
is that it answers the question a headline-sentiment model cannot: *is this story telling me
something new, or is it telling me the stock already moved?* Benzinga publishes both, all day, and
they look almost identical to a keyword model.

| question | type | what it is for |
|---|---|---|
| `relevance` | choice | the roundup filter — with a probability, not a yes/no |
| `direction` | choice | `p(bullish) − p(bearish)` is a calibrated net, not a 1-10 guess |
| `timing` | choice | **the core one**: new information / follow-up / a report of a move |
| `event_type` | choice | thirteen types, for free grouping |
| `materiality` | score | how much this *should* move the stock |
| `surprise` | score | expected-and-priced-in vs genuinely new |
| `reports_price_move` | noul | the calibrated version of a "shares jumped" regex |
| `first_disclosure` | noul | first public report of the fact |
| `company_is_source` | noul | the company said it (PR/filing) vs someone writing about it |
| `is_speculation` | noul | rumour, "reportedly", unconfirmed |

Jev is asked **nothing it is documented to be bad at**: no arithmetic, no date comparison, no
multi-step reasoning. Every one is a judgment a markets reader makes in a second. The numbers that
follow from the answers — thresholds, aggregation, a final label — stay in code, where they can be
tested.

To change what is classified: edit `QUESTIONS`, map any new answer in `to_row`, and **bump NAME**
(`jev-news-v1` -> `jev-news-v2`). Stored judgments are keyed by (item, set name, model), so rows
under one name must all have come from the same questions.
"""

from __future__ import annotations

from typing import Any, Dict

from jevlab.jev import Choice, Noul, QuestionSet, Score, truncate

NAME = "jev-news-v1"

EVENT_TYPES = ("earnings", "guidance", "m&a", "analyst", "product", "contract", "regulatory",
               "legal", "offering", "management", "macro", "roundup", "other")

QUESTIONS: Dict[str, Any] = {
    "relevance": Choice(
        instructions="Is the story ABOUT the subject company?",
        criteria={
            "primary": "The story is about this company, or it is one of its main subjects. You "
                       "could write a headline about this company alone from it.",
            "mentioned": "A passing reference: a comparison, a peer, a supplier, a customer, one "
                         "name in a short list, a quote about someone else.",
            "irrelevant": "Boilerplate: an index-membership note, an ETF holding, an 'other "
                          "movers' tail, or the wire mis-tagged it.",
        }),
    "direction": Choice(
        instructions="For the subject company's share price, is what this story says good, bad or "
                     "neither?",
        criteria={
            "bullish": "A reasonable reader takes this as good news for the share price.",
            "bearish": "A reasonable reader takes this as bad news for the share price.",
            "neutral": "Two-sided, already known, procedural, or it says nothing about the "
                       "company's prospects. A share price moving is not itself good or bad news.",
        }),
    "timing": Choice(
        instructions="When does this story sit relative to the market learning the news about the "
                     "subject company?",
        criteria={
            "new_info": "It discloses a fact the market plausibly did not have before this story: "
                        "an earnings release, a filing, a deal, a regulatory decision, a rating "
                        "change issued now, a guidance change.",
            "follow_up": "Analysis, commentary, a transcript, a recap or a round-up about an event "
                         "that was ALREADY public.",
            "reactive": "The story is ABOUT the share price moving: 'shares are trading higher', "
                        "'why X stock is down today', 'stocks moving in the pre-market'. It "
                        "reports a move that has already happened.",
        }),
    "event_type": Choice(
        instructions="What kind of news is this for the subject company?",
        criteria={
            "earnings": "A reported quarter or year: results, EPS, revenue, a transcript.",
            "guidance": "An outlook or forecast the company gave or changed.",
            "m&a": "A merger, acquisition, takeover, divestiture or stake purchase.",
            "analyst": "A broker or analyst rating, price target or initiation.",
            "product": "A launch, an unveiling, a product or service announcement.",
            "contract": "A customer win, an order, a partnership or a supply deal.",
            "regulatory": "A regulator, an approval, a trial result, an investigation by an agency.",
            "legal": "A lawsuit, a court ruling, a settlement, a fraud claim.",
            "offering": "Raising capital: a share or debt offering, dilution, a buyback.",
            "management": "An executive or board appointment or departure.",
            "macro": "Rates, inflation, tariffs, commodities or the market as a whole.",
            "roundup": "A list of several stocks: movers, 'stocks to watch', a screen.",
            "other": "None of the above.",
        }),
    "materiality": Score(
        instructions="How much should this news move the subject company's share price? Judge the "
                     "EVENT, not how excited the headline sounds.",
        criteria=[
            "A listicle row, an 'other movers' mention, an index-membership note.",
            "A single analyst note, minor PR, a conference appearance, a routine filing.",
            "Guidance commentary, a product launch, a notable contract, an insider purchase.",
            "An earnings beat or miss, a major contract, a large buyback, a CEO departure.",
            "M&A, an FDA decision, a fraud probe, bankruptcy, a guidance reset, an index "
            "add or delete.",
        ]),
    "surprise": Score(
        instructions="How surprising is this to someone who followed the subject company "
                     "yesterday?",
        criteria=[
            "Already public: a recap, a transcript, or a restatement of known facts.",
            "Expected and on the calendar, and it landed roughly where expected.",
            "On the calendar, but the content differs from what was expected.",
            "Not expected, but the kind of thing that happens often for this sort of company.",
            "Genuinely unexpected: nobody following this company yesterday saw it coming.",
        ]),
    "reports_price_move": Noul(
        instructions="The story is reporting that the subject company's share price has already "
                     "moved.",
        criteria={"true": "It states or explains a price or volume move that has happened: "
                          "'shares are trading higher', 'stock jumps 12%', 'here's why X is "
                          "falling', a movers list.",
                  "false": "It reports an event, a decision or an opinion, even if a move may "
                           "follow."}),
    "first_disclosure": Noul(
        instructions="This story is the first public report of the fact it carries about the "
                     "subject company.",
        criteria={"true": "The fact appears to be disclosed here — a release, a filing, an "
                          "exclusive, a rating issued now.",
                  "false": "It repeats, recaps or analyses something already reported."}),
    "company_is_source": Noul(
        instructions="The information comes from the subject company itself — its press release, "
                     "filing, executives or earnings call — rather than from a third party.",
        criteria={"true": "The company announced, filed, reported or said it.",
                  "false": "An analyst, a regulator, a journalist, a rival or an anonymous "
                           "source."}),
    "is_speculation": Noul(
        instructions="The key claim about the subject company is unconfirmed: a rumour, a report "
                     "from anonymous sources, 'reportedly', a possibility being weighed.",
        criteria={"true": "Unconfirmed, attributed to sources, or framed as something that may "
                          "happen.",
                  "false": "Confirmed and on the record."}),
}


def state(item: Dict[str, Any], *, body_chars: int = 1200) -> Dict[str, Any]:
    """The facts one judgment reads: the story, and WHICH company it is being judged for.

    Tight on purpose. The other tagged tickers ARE included, though — "this story names nineteen
    other companies" is exactly the evidence `relevance` needs to call a roundup a roundup.
    """
    others = list(item.get("other_tickers") or [])
    return {
        "subject_ticker": item["subject_ticker"],
        "subject_company": item.get("subject_name") or item["subject_ticker"],
        "published": item.get("published_et") or "",
        "publisher": item.get("source") or "",
        "headline": truncate(item.get("headline"), 300),
        "summary": truncate(item.get("summary"), 600),
        "body": truncate(item.get("body"), body_chars),
        "other_tickers_tagged": others,
        "tickers_tagged_count": len(others) + 1,
    }


def to_row(answers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Answers -> flat columns. Nothing is rounded away; the probabilities keep their own keys."""
    ch = lambda q: (answers.get(q) or {}).get("choice")                      # noqa: E731
    pr = lambda q: (answers.get(q) or {}).get("probabilities") or {}         # noqa: E731
    cf = lambda q: (answers.get(q) or {}).get("confidence")                  # noqa: E731
    sc = lambda q: (answers.get(q) or {}).get("score")                       # noqa: E731
    nl = lambda q: (answers.get(q) or {}).get("noul")                        # noqa: E731

    p_bull, p_bear = pr("direction").get("bullish"), pr("direction").get("bearish")
    materiality = sc("materiality")
    event = ch("event_type")
    net = None if p_bull is None or p_bear is None else p_bull - p_bear
    return {
        "relevance": ch("relevance") or "mentioned",
        "sentiment": ch("direction") or "neutral",
        "timing": ch("timing"),
        "event_type": event if event in EVENT_TYPES else "other",
        # `score` is 1-10 directional CONVICTION: the probability of the direction jev picked,
        # which is the same quantity stated honestly. `impact` is materiality (0-4) on the same
        # 1-10 scale, so the two read side by side.
        "score": to_1_10(max(p_bull or 0.0, p_bear or 0.0)) if net is not None else 1,
        "impact": to_1_10((materiality or 0) / 4.0),
        "p_bull": p_bull, "p_bear": p_bear, "p_neutral": pr("direction").get("neutral"),
        "net_p": net,
        "conf_relevance": cf("relevance"), "conf_direction": cf("direction"),
        "conf_timing": cf("timing"),
        "p_primary": pr("relevance").get("primary"),
        "p_reactive": pr("timing").get("reactive"),
        "p_new_info": pr("timing").get("new_info"),
        "materiality": materiality, "surprise": sc("surprise"),
        "reports_move_p": nl("reports_price_move"),
        "first_disclosure_p": nl("first_disclosure"),
        "company_source_p": nl("company_is_source"),
        "speculation_p": nl("is_speculation"),
    }


def to_1_10(unit: float) -> int:
    """A 0-1 probability -> the 1-10 integer the shared column carries."""
    return max(1, min(10, int(round((unit or 0.0) * 9)) + 1))


SET = QuestionSet(
    name=NAME, questions=QUESTIONS, state=state, to_row=to_row,
    title="Market news",
    describe="per (story, company): relevance, direction, timing, event type, materiality, "
             "surprise, and four true/false likelihoods",
    columns=tuple(to_row({}).keys()))
