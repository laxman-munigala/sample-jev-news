# jev lab

**A hands-on demo of TypeSafe's `jev`: a model that returns typed, calibrated numbers instead of text.**

Pick a real news story or a real X post. See the exact facts the model is given and the exact
questions it is asked — options, rubric levels and all. Press a button. Watch ten classifications
come back at once as probabilities you could threshold in code, in about half a second, for a
fraction of a cent.

Everything runs against a **sample database committed to this repository**: 100 market news
stories and 100 X posts, with every judgment already computed. Clone it and the app works —
an API key only becomes necessary when you want to re-run a judgment yourself.

```bash
git clone <this repo> && cd jev-lab
uv sync
uv run streamlit run app.py          # http://localhost:8501
```

The only credential the project can use is `TYPESAFE_API_KEY`, and it is optional:

```bash
export TYPESAFE_API_KEY=sk-...       # or put it in a .env file at the project root
```

No other service is contacted, ever. No scraping, no news API, no LLM, no cloud secrets — the data
is already in `data/sample.db`.

---

## What is jev?

`jev` is a **judgment model**, not a generative one. You hand it a *state* — some facts — and a set
of *typed questions*. It hands back calibrated numbers. It cannot write you a paragraph, and it
**cannot return a value outside the type you declared**.

That single constraint is what makes it usable as infrastructure rather than as a feature. Ask an
LLM to classify something and you get prose you must parse, in a shape you must validate, at a
price and a latency that turn "classify ten thousand rows" into a project. Ask jev and you get:

```json
{"type": "choice", "choice": "reactive", "confidence": 1.0,
 "probabilities": {"reactive": 1.0, "new_info": 0.0, "follow_up": 0.0}}
```

— already a number, already in range, in ~500 ms, at **$0.042 per million input tokens** with **no
output tokens billed at all**.

### The three primitives

This is the entire vocabulary. Every question in this project is one of these.

| primitive | you declare | you get back |
|---|---|---|
| **`Choice`** | N named options, each with a description | the winning option, a confidence, and a probability on *every* option |
| **`Score`** | an ordered rubric, one description per level | a **weighted position** on it (2.7, not 3), plus the probability mass at each level |
| **`Noul`** | one statement, and what true/false mean | how true it is, 0 to 1 |

`Score` is the one people underuse. Because the answer is weighted rather than rounded, "between
level 2 and level 3" survives into your data instead of being thrown away at the boundary.

### The division of labour

| | does what |
|---|---|
| **jev** | the judgments — is this relevant, which way does it lean, how material is it, how true is this statement |
| **your code** | everything numeric that follows — thresholds, weights, aggregation, the final label |
| **an LLM** | only what genuinely needs prose — a rationale, a summary, a written brief |

Nothing in this project asks jev to do arithmetic, compare dates, or reason in several steps.
Those are its documented weaknesses, and they are also exactly what ordinary Python is best at. The
composite scores you see in the UI (`signal`, `substance`, `impact`) are all plain functions in
`jevlab/qsets/`, computed *from* jev's calibrated outputs — readable, testable, and tunable without
touching the model.

---

## The two demonstrations

Each has its own document, with every question written out and an explanation of what it is for:

| | question sets | document |
|---|---|---|
| **Market news** — 100 Benzinga stories | `jev-news-v1` | **[docs/NEWS.md](docs/NEWS.md)** |
| **X posts** — 50 markets + 50 AI | `jev-x-stocks-v1`, `jev-x-ai-v1` | **[docs/X_POSTS.md](docs/X_POSTS.md)** |

The X side ships **two** question sets over one table on purpose. A markets post and an AI post
are the same kind of object, and the two sets share not one question — because a question set
encodes *what this reader wants to know*, not "how to classify a tweet".

---

## The four screens

**📰 News** — 100 stories, filterable by kind. Pick one and you get the story, the state jev will
read, the ten questions with all their options, a **Run jev** button, and then every answer drawn
by primitive: choices with their full probability distribution, scores against their rubric, nouls
as 0–1 likelihoods. Below that, the columns the application actually stores, and the raw API
response.

**𝕏 X posts** — the same flow over two feeds, each with its own question set. Switch feeds and
compare what the two sets are even asking.

**⚡ Batch** — judge a whole dataset with `judge_many`, over a thread pool, with a progress bar.
Shows items/second, total tokens, total cost, the distribution of every classification, and a
sortable table you can download as CSV. This is the tab that makes the economics concrete.

**📘 How jev works** — the explanation above, plus a playground: type any text, declare a Choice,
Score or Noul in the browser, and run it live.

---

## What it costs

Measured on this corpus, not estimated:

| | items | wall time | input tokens | cost |
|---|---|---|---|---|
| `jev-news-v1` | 100 stories × 10 questions | 2.6 s | 212,896 | **$0.0089** |
| `jev-x-stocks-v1` | 50 posts × 10 questions | 1.5 s | 89,203 | **$0.0037** |
| `jev-x-ai-v1` | 50 posts × 10 questions | 1.7 s | 80,307 | **$0.0034** |
| **total** | **2,000 classifications** | **5.9 s** | **382,406** | **$0.016** |

Two thousand typed classifications for about a cent and a half, in under six seconds on eight
workers. A single judgment is ~200–500 ms. Reproduce it yourself with
`uv run python scripts/precompute.py --redo`.

The reason ten questions are nearly free is architectural: **one judgment is one HTTP call**
carrying the state and every question together, evaluated against the same state in parallel
server-side. Ten questions cost barely more than one, which is why a `QuestionSet` is a bundle and
not ten calls.

---

## How the code is laid out

```
app.py                      the Streamlit entry point
jevlab/
  jev/client.py             credentials, one call per judgment, the thread pool, cost accounting
  jev/questions.py          the QuestionSet type: name, questions, state(), to_row()
  qsets/news.py             jev-news-v1        ← edit the news classifiers here
  qsets/x_stocks.py         jev-x-stocks-v1    ← the markets feed
  qsets/x_ai.py             jev-x-ai-v1        ← the AI feed
  db.py                     three tables, and the judgment cache
  ui/                       the four screens, and one shared answer renderer
scripts/
  build_sample_db.py        how data/sample.db was curated (provenance; you need not run it)
  precompute.py             the pass that filled the shipped judgments
data/sample.db              100 news + 100 X posts + 200 judgments, committed
docs/NEWS.md                every news question, and what it is for
docs/X_POSTS.md             every X question, for both feeds
DEV.md                      design decisions, assumptions, test results, and what is not here
```

`jevlab/jev/` knows nothing about news or X. The only domain-specific code in the project is the
three files in `jevlab/qsets/`.

### Using it in your own code

```python
from jevlab.jev import JevClient
from jevlab.qsets import news

item    = {...}                                      # your row
state   = news.state(item)                           # the facts jev reads — keep it tight
answers = JevClient().judge(state, news.QUESTIONS)   # ONE call, all ten questions
row     = news.to_row(answers)                       # -> your columns, ready to store

if row["timing"] == "reactive" and row["p_reactive"] > 0.8:
    skip(item)                                       # a threshold in code, on a calibrated number
```

### Writing your own question set

1. Copy `jevlab/qsets/x_ai.py`. It is about 200 lines and two thirds of that is the questions.
2. Write `QUESTIONS` — a dict of `Choice` / `Score` / `Noul`. **Every option needs a description**;
   the descriptions *are* the classifier, and there is no prompt hiding behind them.
3. Write `state()`. Keep it tight — a bloated state full of things the questions never use is
   jev's documented failure mode, not a safety margin.
4. Write `to_row()`: the answers → flat columns. Put your thresholds and composites here, in code.
5. **Name it, and version the name.** Stored judgments are keyed by *(item, set name, model)*, so
   every row under one name must have come from the same questions. Change a question → bump
   `jev-x-ai-v1` to `-v2`. Otherwise two incomparable things sit in one column and nobody notices.

---

## About the sample data

`data/sample.db` is a frozen snapshot, carved out of a private research database and committed
here so the project has no runtime dependencies at all.

* **News** — 100 Benzinga stories from late August to mid-September 2026, each paired with the
  company the judgment is *about*. Chosen by quota across twelve kinds of story, not at random:
  100 random stories would be sixty near-identical analyst notes and the demo would teach nothing.
* **X posts** — 100 public posts from two curated X lists, 50 each, kept exactly as they were
  scraped: real handles, real text, real engagement numbers. Chosen by quota across post kinds,
  and capped so no single account owns more than a fifth of a feed.
* **Judgments** — 200 rows, produced by `jev-1.13.0` and stored under that concrete version rather
  than the `jev-latest` alias that was requested, so a future model's judgments land *beside*
  these instead of silently replacing them.

Nothing is fetched at runtime. `scripts/build_sample_db.py` documents exactly how the rows were
selected; it needs the original private database and is kept for provenance, not for you to run.

---

## License and attribution

The code here is a demo, free to copy. The news stories are Benzinga's and the X posts are their
authors'; both are included as a fixed sample for illustration.
