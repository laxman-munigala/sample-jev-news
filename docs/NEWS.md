# `jev-news-v1` — judging market news

**Source:** `jevlab/qsets/news.py` · **Data:** 100 Benzinga stories in `data/sample.db` ·
**Model:** `jev-1.13.0`

---

## The problem this set exists for

A financial newswire publishes two kinds of story that look almost identical to any keyword model:

> **"Firefly Landed a $100 Million NASA Contract This Month"**
> **"12 Information Technology Stocks Moving In Friday's After-Market Session"**

The first tells you something. The second tells you the market already moved — it is a *record* of
a price change, published after the fact, and treating it as a signal means buying the top all day.
Both mention companies, both carry positive language, both get tagged with tickers by the wire.

Worse, the second one is tagged with **twelve** tickers, and the story is not really "about" any of
them. A sentiment score attached to each of those twelve is twelve pieces of noise.

So this set asks ten questions per **(story, company)** pair, and the two load-bearing ones are
`timing` and `relevance`.

---

## The ten questions

One HTTP call per pair carries all ten; they are evaluated against the same state in parallel.

### `relevance` — Choice

> *Is the story ABOUT the subject company?*

| option | when |
|---|---|
| `primary` | The story is about this company, or it is one of its main subjects. You could write a headline about this company alone from it. |
| `mentioned` | A passing reference: a comparison, a peer, a supplier, a customer, one name in a short list, a quote about someone else. |
| `irrelevant` | Boilerplate: an index-membership note, an ETF holding, an 'other movers' tail, or the wire mis-tagged it. |

This is the roundup filter — but *with a probability*, so downstream code can pick its own
threshold instead of inheriting someone's boolean.

### `direction` — Choice

> *For the subject company's share price, is what this story says good, bad or neither?*

`bullish` · `bearish` · `neutral`

The useful output is not the label but `p(bullish) − p(bearish)`, a calibrated net stored as
`net_p`. A story at 0.51/0.49 and one at 0.99/0.01 both come back "bullish"; only the probabilities
tell you which one to act on.

Note the criterion on `neutral`: *"A share price moving is not itself good or bad news."* Without
it, every "shares jump 12%" recap scores maximally bullish.

### `timing` — Choice · **the core question**

> *When does this story sit relative to the market learning the news?*

| option | when |
|---|---|
| `new_info` | Discloses a fact the market plausibly did not have: an earnings release, a filing, a deal, a regulatory decision, a rating change issued now, a guidance change. |
| `follow_up` | Analysis, commentary, a transcript, a recap or a round-up about an event that was ALREADY public. |
| `reactive` | The story is ABOUT the share price moving: "shares are trading higher", "why X stock is down today". It reports a move that has already happened. |

### `event_type` — Choice

Thirteen options — `earnings`, `guidance`, `m&a`, `analyst`, `product`, `contract`, `regulatory`,
`legal`, `offering`, `management`, `macro`, `roundup`, `other` — for grouping. It comes free with
the call, so there is no reason not to ask.

### `materiality` — Score (0–4)

> *How much should this news move the share price? Judge the EVENT, not how excited the headline sounds.*

| level | description |
|---|---|
| 0 | A listicle row, an 'other movers' mention, an index-membership note. |
| 1 | A single analyst note, minor PR, a conference appearance, a routine filing. |
| 2 | Guidance commentary, a product launch, a notable contract, an insider purchase. |
| 3 | An earnings beat or miss, a major contract, a large buyback, a CEO departure. |
| 4 | M&A, an FDA decision, a fraud probe, bankruptcy, a guidance reset, an index add or delete. |

The clause "judge the EVENT, not how excited the headline sounds" is doing real work: financial
media writes every story in the same register.

### `surprise` — Score (0–4)

> *How surprising is this to someone who followed the company yesterday?*

From "already public: a recap or a restatement of known facts" up to "genuinely unexpected: nobody
following this company yesterday saw it coming". This is the axis a sentiment rubric usually
lacks — an expected, on-calendar, in-line earnings print is material *and* unsurprising, and those
are two different facts about it.

### The four nouls (0–1)

| noul | the statement being weighed |
|---|---|
| `reports_price_move` | The story is reporting that the share price has already moved. |
| `first_disclosure` | This story is the first public report of the fact it carries. |
| `company_is_source` | The information comes from the company itself — its release, filing, executives or call — rather than a third party. |
| `is_speculation` | The key claim is unconfirmed: a rumour, anonymous sources, "reportedly", a possibility being weighed. |

`reports_price_move` is the calibrated replacement for a regex over "shares jumped|stock soars|
here's why". The regex is a boolean that is wrong at the margin; the noul is 0.91 and you choose
the margin.

`is_speculation` and `first_disclosure` deliberately pull in opposite directions, and the model
handles it: on the sample's Anthropic/OpenAI story, `is_speculation` = **0.94** while
`first_disclosure` = **0.16** — unconfirmed, *and* not the first place it was reported.

---

## What the code does with the answers

`to_row()` in `jevlab/qsets/news.py` flattens the answers into columns. Everything numeric in it
is plain Python — jev supplied the calibrated inputs, and the arithmetic stays somewhere it can be
read and tested.

| column | from |
|---|---|
| `relevance`, `sentiment`, `timing`, `event_type` | the four choices, as labels |
| `p_bull`, `p_bear`, `p_neutral`, `net_p` | the `direction` distribution, and `p_bull − p_bear` |
| `p_primary`, `p_reactive`, `p_new_info` | individual probabilities worth thresholding directly |
| `conf_relevance`, `conf_direction`, `conf_timing` | per-question confidence |
| `materiality`, `surprise` | the raw 0–4 weighted scores |
| `score` | 1–10 **directional conviction**: `max(p_bull, p_bear)` rescaled — the same quantity, stated honestly |
| `impact` | `materiality / 4` on the same 1–10 scale, so the two read side by side |
| `reports_move_p`, `first_disclosure_p`, `company_source_p`, `speculation_p` | the four nouls |

A pipeline built on this would read, in full:

```python
row = news.to_row(answers)
if row["relevance"] == "irrelevant" or row["p_primary"] < 0.35:
    return                                      # not about this company
if row["timing"] == "reactive" and row["p_reactive"] > 0.8:
    return                                      # the move already happened
if row["impact"] >= 6 and abs(row["net_p"]) > 0.5:
    alert(row)
```

Every threshold is visible, adjustable, and testable. None of them is inside the model.

---

## Does it work? Measured on the sample

The 100 stories were bucketed by hand-written regex over headlines *before* anything was judged
(see `scripts/build_sample_db.py`). Those labels are only a rough curation aid — but they give an
independent axis to check the judgments against:

| curated bucket | `reactive` | `follow_up` | `new_info` |
|---|---|---|---|
| **price_move** (12) | **12** | — | — |
| **transcript** (6) | — | **6** | — |
| roundup (8) | — | 6 | 2 |
| product_contract (8) | 2 | 1 | **5** |
| analyst (10) | — | 4 | **6** |
| earnings (10) | 2 | **6** | 2 |
| m_and_a (8) | 4 | 2 | 2 |

Both extremes are clean: **every** story whose headline advertises a price move is `reactive`, and
**every** earnings-call transcript is `follow_up`. The middle rows are where it gets interesting —
an "earnings" story is `follow_up` more often than `new_info`, because most earnings coverage is
written *after* the release and recaps it. That is correct, and it is not what a keyword rule
would have said.

`relevance` over the same 100 stories: **50 primary · 26 mentioned · 24 irrelevant**. A quarter of
the (story, ticker) pairs the wire produced are not worth a sentiment score at all — which is the
single most valuable thing this set tells you, and it costs $0.0089 to learn for the whole corpus.

---

## Changing the questions

Edit `QUESTIONS` in `jevlab/qsets/news.py`, map any new answer in `to_row()`, and then — the
load-bearing step — **bump `NAME` from `jev-news-v1` to `jev-news-v2`.**

Judgments are stored keyed by *(item, set name, model)*. Rows under one name must all have come
from the same questions, or a column silently mixes two incomparable things. Bumping the name also
means the old judgments stay queryable and the two versions can be compared side by side, which is
the only honest way to tell whether a re-worded criterion helped.
