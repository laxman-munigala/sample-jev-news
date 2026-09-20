# DEV.md — how this was built, what was decided, and what was left out

A working log for whoever picks this up next (including me). The user-facing documents are
[README.md](README.md), [docs/NEWS.md](docs/NEWS.md) and [docs/X_POSTS.md](docs/X_POSTS.md).

---

## Goal

A self-contained project to show a professional audience **what jev is and how to use it**. It had
to run from a clone with no setup beyond `uv sync`, depend on nothing but the TypeSafe API, and
make the *point* of a judgment model obvious rather than merely demonstrate that an API call
returns JSON.

## The four decisions that shaped it

| decision | why |
|---|---|
| **Ship pre-computed judgments in the committed DB** | Someone you send this to can browse 200 real judgments, with probabilities, before deciding whether to get a key. A demo that shows an empty screen without credentials does not get shared. |
| **Keep the X posts exactly as scraped** — real handles, text, engagement | They are public posts, and anonymised sample data reads as fake, which undercuts the whole argument. Noted in the README as a frozen snapshot. |
| **Two separate X question sets, not one shared one** | The strongest teaching point in the repo: two feeds of identical *shape* need entirely different questions. One "X classifier" would have taught the opposite lesson. |
| **Curate the 100 + 100 by quota, not at random** | 100 random Benzinga stories are ~60 near-identical analyst notes. Quotas across twelve story kinds put a movers roundup next to a genuine disclosure, which is where the model visibly discriminates. |

## Assumptions made (unprompted, by design)

1. **Package name `jevlab`, project name `jev-lab`.** The repo directory is `sample-jev-news`, but
   the project covers X posts too and a shareable name reads better.
2. **No installable package.** `tool.uv.package = false`; `jevlab/` sits next to `app.py` and is
   imported directly. One less concept between a reader and the code.
3. **Credentials from the environment only.** The source project also read GCP Secret Manager;
   that was stripped. One key, one place.
4. **Three tables, not two.** The brief said "maybe two tables"; `judgments` is the third and it is
   load-bearing — it is what makes the shipped judgments possible.
5. **Committed `.streamlit/config.toml`** with a light theme, so everyone sees the same app.
6. **Composite scores (`signal`, `substance`) invented for the X sets.** There was no prior art to
   copy, and they demonstrate the house rule — jev supplies calibrated inputs, *code* does the
   arithmetic — better than another raw column would.
7. **`is_about_typesafe` noul in the AI set.** The scraped feed happened to be arguing about jev
   at the time. Too good a demonstration to leave out.
8. **Model alias `jev-latest` requested; concrete version stored.** Judgments are keyed by
   `jev-1.13.0`, so a future version's rows land beside these instead of overwriting them.

## Bugs found and fixed while testing

| bug | cause | fix |
|---|---|---|
| Per-item `input_tokens` inflated ~8× | `judge_one` measured `client.input_tokens` before/after, but eight pool threads share that counter | `_call()` returns its own call's usage; `judge_one` uses it. Totals now reconcile exactly with the client's own accounting |
| `NoSessionContext` crash on every batch run | `judge_many`'s `on_result` fires on worker threads; Streamlit's progress bar needs the script-run context | The batch tab chunks the queue and advances the bar on the main thread between chunks. Caveat documented on `judge_many` |
| X post cards rendered as raw HTML | Streamlit parses markdown before raw HTML, so a newline inside a `<div>` ends the HTML block — and X posts are mostly newlines | `render.block()` converts newlines to `<br>` |
| Dataframe columns collapsed on the X and Batch screens | Streamlit renders **every** `st.tabs` pane on every rerun, and a dataframe laid out while hidden measures zero width | Replaced `st.tabs` with `st.segmented_control`; only the visible section renders (also makes each rerun cheaper) |
| "nearest level" blank in the playground only | A Score's `legend`/`probabilities` come back keyed by **int**; JSON has no int keys, so cached answers were keyed by `"3"` and live ones by `3` | `plain()` forces mapping keys to `str`, so live and cached answers are one shape |
| Layout overflowed / wasted half a wide monitor | Streamlit caps even its wide layout at 1400px; my own `max-width` override was less specific than its rule | `max-width: min(1860px, 97%) !important` |
| `StreamlitAPIException: "✓" is not a valid emoji` | `st.success(icon=...)` requires a real emoji | Used ✅ / ⚠️ |
| Selection caption was wrong | `st.dataframe` single-row selection needs the checkbox; clicking a cell only focuses it | Caption now says "tick a box to select" |

## Test results

**Data build** (`scripts/build_sample_db.py`) — 100 news + 100 X posts, every quota filled, all 100
news items carry a real company name (the last 46 are extracted from Benzinga's own
`Company Name (NASDAQ: TICK)` pattern rather than hand-written).

**Full judgment pass** (`scripts/precompute.py --redo`), `jev-1.13.0`:

| set | items | wall | tokens | cost | failures |
|---|---|---|---|---|---|
| `jev-news-v1` | 100 | 2.6 s | 212,896 | $0.0089 | 0 |
| `jev-x-stocks-v1` | 50 | 1.5 s | 89,203 | $0.0037 | 0 |
| `jev-x-ai-v1` | 50 | 1.7 s | 80,307 | $0.0034 | 0 |

**Does it discriminate?** Checked against the curation buckets, which were assigned by regex
*before* any judgment was made:

* 12/12 `price_move` stories → `timing = reactive`
* 6/6 `transcript` stories → `timing = follow_up`
* `relevance` over 100 stories: 50 primary / 26 mentioned / 24 irrelevant
* `is_about_typesafe` top four are all genuinely jev posts (0.87–0.96); no keyword list involved
* `signal` bottoms out at 0.00 on two subscription-funnel posts from large verified accounts that
  engagement metrics would have ranked highly

**UI, exercised in a browser:**

| | result |
|---|---|
| News: filter, search, select, cached judgment | ✅ |
| News: **Run jev live** | ✅ 436 ms, fresh probabilities, row replaced in DB |
| X: both feeds, both question sets, cards, selection | ✅ |
| Batch: live run of 25 | ✅ 1.1 s, 22.3 items/s over 8 workers, $0.0023 |
| Batch: metrics, four distribution charts, sortable table, CSV download | ✅ |
| Playground: Score on a support ticket | ✅ 3.85/4 urgency, 0.85 mass on level 4 |
| Sidebar: key detection, coverage, live session spend | ✅ |
| No-key path | Buttons disable, stored judgments still browse (verified by unsetting the variable) |

## Known limitations

* **Streamlit reruns the whole script on every widget change.** With a 100-row corpus this is
  imperceptible; it is not an architecture for a large table.
* **The selection table needs a checkbox click**, which is a Streamlit dataframe behaviour, not a
  choice. The caption says so.
* **The composite weights are unvalidated.** `signal` and `substance` are illustrative — they show
  *where* such a formula belongs, not what the right coefficients are.
* **The curation buckets are regex over headlines.** They are a sampling aid and a rough
  cross-check, not ground truth. Where a judgment disagrees with a bucket, the judgment is usually
  the better label.
* **`scripts/build_sample_db.py` cannot be re-run from a clone** — it needs the private research
  database. It is committed for provenance.
* **One judgment per story**, always for the story's best-matching tagged company. The production
  version judges every (story, ticker) pair; here that would be 16,000 judgments and a worse demo.

## Possible next steps

* A **v2 of a question set beside v1**, judged over the same items, with the UI diffing them. The
  repo is already keyed for it (`judgments` is keyed by set name *and* model) and it would make
  the versioning argument concrete rather than stated.
* **A ground-truth column** on 30 or so stories, hand-labelled, plus an agreement number. It would
  turn "look how well it does" into a measurement.
* **A calibration plot** — bucket by predicted probability, show observed frequency. The most
  honest thing you can show about a model that returns probabilities.
* **Price bars after each story**, to test whether `timing = new_info` actually precedes a move.
  That is the backtest the source project exists for and it is out of scope here.
* A **cost comparison tab** running the same classification through an LLM, side by side on tokens,
  latency and agreement.

## Working notes

* Restart Streamlit after editing anything under `jevlab/` — the watcher does not always reload an
  imported module, and you will debug CSS that is not running.
* `uv run python scripts/precompute.py --limit 3` is the cheap smoke test for all three sets.
* `uv run python scripts/build_sample_db.py --drop-judgments` rebuilds the corpus from scratch;
  without the flag it carries existing judgments across, which is almost always what you want.
