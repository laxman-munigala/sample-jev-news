# `jev-x-stocks-v1` and `jev-x-ai-v1` — judging X posts

**Source:** `jevlab/qsets/x_stocks.py`, `jevlab/qsets/x_ai.py` ·
**Data:** 100 public X posts in `data/sample.db` (50 per feed) · **Model:** `jev-1.13.0`

---

## Why two question sets over one table

The 100 posts come from two curated X lists. Structurally they are identical rows — an author,
some text, a timestamp, four engagement counters. It would be easy, and wrong, to write one "X
post classifier" for both.

Nobody reading a markets list wants to know a post's *novelty*. Nobody reading an AI list wants it
labelled *bullish*. The two feeds are read for different reasons, so they get different questions
and different names:

| feed | set | the question it is really asking |
|---|---|---|
| Markets list | `jev-x-stocks-v1` | Is there a call here, which way, and how much weight does it deserve? |
| AI list | `jev-x-ai-v1` | Is there information here, and what is it standing on? |

**The two sets share not a single question.** That is the design lesson: a `QuestionSet` encodes
what *this* reader wants to know. It is not a reusable classifier, and it is versioned by name so
the answers stored under it always mean one thing.

What *is* shared is the shape. `reacts_to_price_move` in the markets set and `reports_price_move`
in [`jev-news-v1`](NEWS.md) are the same judgment about a different object — which is what porting
a question set to a new domain looks like, as opposed to reinventing one.

---

# `jev-x-stocks-v1` — the markets feed

A curated finance list is perhaps 15% signal. The rest is trading psychology, motivational
posting, charts with no thesis, and subscription funnels. All of it is written confidently, and a
good share of it carries a cashtag, so neither tone nor keywords separate it.

### The ten questions

#### `post_type` — Choice · the noise filter

| option | when |
|---|---|
| `trade_call` | A specific position or trade: buying, selling, adding, trimming, a level, an entry, a target. |
| `analysis` | A thesis or read on a company or asset: what it is worth, why it moves, what the chart or numbers say. |
| `news_relay` | Relaying a fact that happened: a contract, a filing, a launch, a print, an earnings number. |
| `market_commentary` | A read on the market, a sector, rates, flows or breadth rather than one name. |
| `education` | A lesson, a rule, trading psychology, a general principle. No position, no current claim. |
| `promotion` | Selling something: a subscription, a newsletter, a course, a Discord, a referral code. |
| `chatter` | Small talk, a joke, a reply fragment, a photo. Nothing about an asset. |

#### `subject` — Choice

`single_stock` · `several_stocks` · `sector_or_theme` · `whole_market` · `crypto` · `not_markets`

`not_markets` matters more than it looks: a third of a finance feed is not about markets at all,
and everything downstream should know that before it computes a sentiment.

#### `stance` — Choice

`bullish` · `bearish` · `neutral`, on whatever the post is about. As with the news set, the value
is `p_bull − p_bear` rather than the label.

#### `horizon` — Choice

`intraday` · `swing` (days to weeks) · `long_term` · `none`. A day-trade tweet and a
five-year thesis are not the same claim even when they name the same stock and lean the same way.

#### `conviction` — Score (0–4)

From "no view at all" through "a musing or a question", "a leaning, hedged", "a clear view stated
plainly", to "emphatic and committed: sized, repeated, 'my largest position'". Explicitly judges
**the commitment in the wording, not whether the view is correct** — jev is reading, not
forecasting.

#### `evidence` — Score (0–4)

What the claim stands on: nothing → the author's own track record → a chart or a level → specific
numbers → **a primary source quoted or linked**.

#### `promotional` — Score (0–4)

From "not selling anything" to "pure funnel: a link, a code, 'join', nothing else".

#### The three nouls (0–1)

| noul | the statement being weighed |
|---|---|
| `is_actionable_call` | A reader could act on this without a follow-up question: it names what, which way, and roughly when. |
| `discloses_position` | The author says they personally hold, are entering, or are exiting. |
| `reacts_to_price_move` | The post is about a move that has ALREADY happened, not one the author expects. |

### The derived `signal` column

`to_row()` combines four calibrated inputs into one number for sorting a feed. This is **code's
opinion**, not jev's — which is exactly where a weighting like this belongs, because it is the
part you will want to argue about and tune:

```python
signal = (conviction/4 * 4.0) + (evidence/4 * 4.0) + is_actionable_call * 2.0
         - (promotional/4 * 3.0)                                   # clamped to 0–10
```

Conviction and evidence earn points, actionability adds, and a sales pitch subtracts. Measured on
the 50 markets posts:

| `signal` | post |
|---|---|
| **7.69** | *"Oppenheimer sees $META Muse reaching $28B of AI agent revenue…"* |
| **5.93** | *"$PLTR just won a $48M U.S. Army contract to replace nine separate…"* |
| **0.00** | *"#factormembers recent posts https://… Join"* |
| **0.00** | *"State of the Market Video https://…/superfollows/subscribe"* |

Both zero-scoring posts are from high-follower, verified accounts and read as confident market
commentary. Engagement would have ranked them highly; `promotional` sank them.

Distribution over the 50 posts — `post_type`: education 14 · analysis 8 · news_relay 8 ·
market_commentary 7 · promotion 6 · chatter 4 · trade_call 3. Only **3 in 50** are actual trade
calls, and `horizon` says 21 of 50 make no time-bound claim at all.

---

# `jev-x-ai-v1` — the AI feed

Same medium, different job. An AI list is not read for direction; it is read to find out whether
anything actually happened. So this set asks about **claim and support**.

### The ten questions

#### `topic` — Choice

`model_release` · `research_result` · `tooling` · `industry` · `opinion` · `banter`

#### `claim_type` — Choice · the load-bearing one

| option | when |
|---|---|
| `announcement` | Something now exists or is available — a fact checkable today. |
| `measured_result` | A number that was measured: a benchmark, a score, a latency, a cost. |
| `firsthand_report` | What happened when the author used it themselves. |
| `secondhand_report` | Relaying what someone else reported, said or published. |
| `prediction` | What will happen, or what something will be worth, later. |
| `opinion` | A judgment with no factual claim attached. |

The `firsthand` / `secondhand` split is where you see calibration do something a label cannot. One
sample post scores **0.45 / 0.45** across the two — the author is describing their own launch
while quoting what someone else said about it, and the honest answer is a coin flip. A hard label
would have picked one and hidden that.

#### `tone` — Choice

`enthusiastic` · `critical` · `neutral`.

#### `novelty` — Score (0–4)

"Everyone has seen this" → "genuinely new: a result, a release or a disclosure that had not
surfaced". Judged against *someone who reads AI news every day*, which is the only frame that
makes the question answerable.

#### `evidence` — Score (0–4)

Nothing → the author's impression → a described experience → concrete figures → **a verifiable
source in the post: a link, a repo, a paper, a screenshot of a run**.

#### `hype` — Score (0–4)

Explicitly **relative to what is being shown**: "superlatives doing the work the evidence is not".
Level 4 is "pure hype: no substance under the excitement". This is why `hype` and `evidence` are
separate questions rather than two ends of one axis — a post can be loud *and* substantiated.

#### The four nouls (0–1)

| noul | the statement being weighed |
|---|---|
| `cites_numbers` | At least one concrete quantitative figure about the technology. |
| `is_firsthand` | The author is reporting their own direct use. |
| `is_promotion` | The author is promoting something they have a stake in. |
| `is_about_typesafe` | The post is about jev / TypeSafe / typed judgment models specifically. |

`is_about_typesafe` is partly a joke and partly the best demonstration in the repo. This feed was
scraped while the list was mid-argument about jev, so the corpus contains a natural cluster to
find. Sort the Batch tab by `typesafe_p` and the top of the list is:

| `typesafe_p` | post |
|---|---|
| 0.96 | *"Okay, everyone wants us to give the unbiased facts. Je…"* |
| 0.90 | *"LLMs vs. Jev, clearly explained! TL;DR…"* |
| 0.89 | *"hear me out: jev, but with the ability to think longer…"* |
| 0.87 | *"putting an early bet that Jev's biggest use will be som…"* |

No keyword list, no regex, no fine-tuning — one sentence describing what you want, and a ranked
probability over every post.

### The derived `substance` column

```python
substance = (novelty/4 * 4.5) + (evidence/4 * 4.5) + is_firsthand * 1.5
            - (hype/4 * 2.5) - is_promotion * 1.5           # clamped to 0–10
```

Top of the 50 AI posts by `substance`: three sourced industry reports (the FT on OpenAI's
spending, Anthropic's outside safety auditor, a WSJ confirmation). Bottom: a pun, a one-line
in-joke, and a rhetorical question from a founder about their own product. That is the ordering
you would want in a feed reader, produced from six calibrated numbers and four lines of
arithmetic.

Distribution over the 50 posts — `topic`: opinion 13 · tooling 10 · industry 8 · model_release 7 ·
research_result 6 · banter 6. `tone`: enthusiastic 25 · critical 14 · neutral 11.

---

## Writing your own

Copy either file. Two thirds of it is the questions, and that is as it should be — **the option
descriptions are the classifier.** There is no prompt behind them, no examples, no system message.
If a classification is wrong, the fix is to write the criterion more precisely, and the diff is
readable by anyone on the team.

The rules that matter:

1. Ask only what a person could answer in a second from the state you give. No arithmetic, no date
   comparison, no multi-step reasoning — those belong in `to_row()`.
2. Keep the state tight. jev degrades on bloat; padding it with context "just in case" makes the
   answers worse, not safer.
3. Every option gets a description, including the boring ones. `neutral` and `other` are where
   miscategorised items pile up when their criteria are vague.
4. Put every threshold, weight and composite in `to_row()`, in Python, where it can be tested.
5. **Version the name.** Change a question → bump `-v1` to `-v2`. Judgments are stored by
   *(item, set name, model)*, and a column that silently mixes two question wordings is worse than
   no column.
