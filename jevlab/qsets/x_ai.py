#!/usr/bin/env python3
"""jevlab/qsets/x_ai.py — `jev-x-ai-v1`: reading an AI/tech X feed.

Same medium as `jev-x-stocks-v1`, completely different question. Nobody reading an AI list wants a
bullish/bearish label; they want to know **whether a post carries information** — a model that
shipped, a number that was measured, something the author actually ran — or whether it is the
hundredth take on a thing everyone already saw. So this set asks about *claim and support*, not
direction.

| question | type | what it is for |
|---|---|---|
| `topic` | choice | release / research / tooling / industry / opinion / joke |
| `claim_type` | choice | the load-bearing one: announcement, measured result, firsthand report, prediction, opinion |
| `tone` | choice | enthusiastic / critical / neutral about its subject |
| `novelty` | score | everyone knew this ... nobody had seen this |
| `evidence` | score | asserted ... numbers ... a link, a repo, a reproducible run |
| `hype` | score | plainly stated ... breathless |
| `cites_numbers` | noul | benchmark scores, token rates, parameter counts, dollars |
| `is_firsthand` | noul | "I ran it", not "I read that someone ran it" |
| `is_promotion` | noul | the author is selling their own thing |
| `is_about_typesafe` | noul | the feed is mid-argument about jev itself — a nice sanity check you can eyeball |

Put this set and the markets set side by side and the design rule falls out: **a question set is
a domain's judgment, not a reusable classifier.** Two feeds of the same shape, two sets, two
names. Neither one is "the X question set".
"""

from __future__ import annotations

from typing import Any, Dict

from jevlab.jev import Choice, Noul, QuestionSet, Score, truncate

NAME = "jev-x-ai-v1"

QUESTIONS: Dict[str, Any] = {
    "topic": Choice(
        instructions="What is this post about?",
        criteria={
            "model_release": "A model, dataset or library that has shipped or is shipping: a "
                             "version, a launch, availability, open weights.",
            "research_result": "A paper, a benchmark, an evaluation, a measured finding, a "
                               "technique.",
            "tooling": "Practical use: an SDK, an agent harness, an IDE, an inference engine, a "
                       "workflow, an integration.",
            "industry": "The business of AI: funding, valuations, hiring, compute deals, "
                        "regulation, an IPO, a lawsuit.",
            "opinion": "A take on where AI is going, what is overrated, how it changes work or "
                       "society.",
            "banter": "A joke, a meme, a one-liner, a reply, a photo. Nothing being claimed.",
        }),
    "claim_type": Choice(
        instructions="What kind of claim is the post making? If it makes several, take the one "
                     "the post is built around.",
        criteria={
            "announcement": "Something now exists or is available. A fact about the world that "
                            "can be checked today.",
            "measured_result": "A number that was measured: a benchmark, a score, a latency, a "
                               "throughput, a cost.",
            "firsthand_report": "What happened when the author used it themselves.",
            "secondhand_report": "Relaying what someone else reported, said or published.",
            "prediction": "What will happen, or what something will be worth, later.",
            "opinion": "A judgment or preference with no factual claim attached.",
        }),
    "tone": Choice(
        instructions="How does the post feel about its subject?",
        criteria={
            "enthusiastic": "Impressed, excited, recommending it.",
            "critical": "Skeptical, disappointed, warning, pushing back.",
            "neutral": "Reporting or describing without taking a side.",
        }),
    "novelty": Score(
        instructions="How new is this to someone who reads AI news every day?",
        criteria=[
            "Everyone has seen this — a restatement of a widely known thing.",
            "Known, but with a small new detail or a better framing.",
            "A development from the last few days that not everyone will have caught.",
            "A specific thing most readers will be learning here for the first time.",
            "Genuinely new: a result, a release or a disclosure that had not surfaced.",
        ]),
    "evidence": Score(
        instructions="What is the post's claim standing on?",
        criteria=[
            "Nothing — assertion, or no claim at all.",
            "The author's impression or taste.",
            "A described experience: what they built, ran or observed, without figures.",
            "Concrete figures: scores, rates, sizes, prices, dates.",
            "A verifiable source in the post: a link, a repo, a paper, a screenshot of a run.",
        ]),
    "hype": Score(
        instructions="How overstated is the language relative to what is actually being shown?",
        criteria=[
            "Flat and factual.",
            "Mild enthusiasm, proportionate.",
            "Strong adjectives, but the substance is there.",
            "Superlatives doing the work the evidence is not: 'insane', 'changes everything'.",
            "Pure hype: no substance under the excitement.",
        ]),
    "cites_numbers": Noul(
        instructions="The post contains at least one concrete quantitative figure about the "
                     "technology: a benchmark score, a percentage, a token rate, a parameter or "
                     "context size, a price, a dollar amount.",
        criteria={"true": "A specific number about the subject appears in the post.",
                  "false": "No figures, or only incidental ones (dates, counts of people)."}),
    "is_firsthand": Noul(
        instructions="The author is reporting their own direct use of the thing.",
        criteria={"true": "They built it, ran it, tested it, integrated it, use it daily.",
                  "false": "They are relaying, commenting on, or reacting to someone else's "
                           "work."}),
    "is_promotion": Noul(
        instructions="The author is promoting something they have a stake in — their product, "
                     "their company's model, their course, their newsletter.",
        criteria={"true": "The post exists to get you to use or buy the author's own thing.",
                  "false": "No stake, or the author's own work is mentioned only in passing."}),
    "is_about_typesafe": Noul(
        instructions="The post is about TypeSafe's Jev model or the idea of typed, "
                     "non-generative judgment models specifically.",
        criteria={"true": "It names Jev, TypeSafe, System One, or nouls, or it is clearly "
                          "discussing that model.",
                  "false": "It is about something else, even if it is about AI models "
                           "generally."}),
}


def state(post: Dict[str, Any], *, text_chars: int = 900) -> Dict[str, Any]:
    return {
        "author": f"@{post.get('author_handle') or 'unknown'}"
                  + (f" ({post['author_name']})" if post.get("author_name") else "")
                  + (" · verified" if post.get("verified") else ""),
        "posted": post.get("posted_at_et") or "",
        "text": truncate(post.get("text"), text_chars),
        "quoted_post": truncate(post.get("quote_text"), 400) or None,
        "engagement": {"likes": post.get("likes", 0), "reposts": post.get("reposts", 0),
                       "replies": post.get("replies", 0), "views": post.get("views", 0)},
    }


def to_row(answers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ch = lambda q: (answers.get(q) or {}).get("choice")                      # noqa: E731
    pr = lambda q: (answers.get(q) or {}).get("probabilities") or {}         # noqa: E731
    cf = lambda q: (answers.get(q) or {}).get("confidence")                  # noqa: E731
    sc = lambda q: (answers.get(q) or {}).get("score")                       # noqa: E731
    nl = lambda q: (answers.get(q) or {}).get("noul")                        # noqa: E731

    novelty, evidence, hype = sc("novelty"), sc("evidence"), sc("hype")

    # "Worth opening?" — code's call, from jev's calibrated inputs. Novelty and evidence earn
    # points, hype that the evidence does not support takes them away.
    substance = None
    if None not in (novelty, evidence, hype):
        substance = round(max(0.0, min(10.0,
            (novelty / 4 * 4.5) + (evidence / 4 * 4.5) + (nl("is_firsthand") or 0) * 1.5
            - (hype / 4 * 2.5) - (nl("is_promotion") or 0) * 1.5)), 2)

    return {
        "topic": ch("topic"), "claim_type": ch("claim_type"), "tone": ch("tone"),
        "substance": substance,
        "p_enthusiastic": pr("tone").get("enthusiastic"),
        "p_critical": pr("tone").get("critical"),
        "p_neutral": pr("tone").get("neutral"),
        "p_banter": pr("topic").get("banter"),
        "p_measured_result": pr("claim_type").get("measured_result"),
        "conf_topic": cf("topic"), "conf_claim_type": cf("claim_type"),
        "novelty": novelty, "evidence": evidence, "hype": hype,
        "numbers_p": nl("cites_numbers"),
        "firsthand_p": nl("is_firsthand"),
        "promotion_p": nl("is_promotion"),
        "typesafe_p": nl("is_about_typesafe"),
    }


SET = QuestionSet(
    name=NAME, questions=QUESTIONS, state=state, to_row=to_row,
    title="X — AI feed",
    describe="per post: topic, claim type, tone, novelty, evidence, hype, and four true/false "
             "likelihoods",
    columns=tuple(to_row({}).keys()))
