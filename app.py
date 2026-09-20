#!/usr/bin/env python3
"""app.py — jev lab: a hands-on tour of TypeSafe's jev judgment model.

    uv run streamlit run app.py

Four tabs. Two of them do the same thing to different data — pick an item, see the exact state
and the exact questions, press a button, watch typed numbers come back. One runs the whole corpus
to show what a hundred judgments cost. One explains the model and lets you write a question of
your own.

The only credential this project needs is `TYPESAFE_API_KEY`, and it is optional: the sample
database ships with every judgment pre-computed, so the app is fully browsable without it.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="jev lab", page_icon="◑", layout="wide",
                   initial_sidebar_state="expanded")

from jevlab import db as store                                     # noqa: E402
from jevlab.jev.client import DEFAULTS, ENV_KEY, have_key          # noqa: E402
from jevlab.ui import batch_tab, learn_tab, news_tab, render, x_tab  # noqa: E402
from jevlab.ui.common import get_db, session_cost                  # noqa: E402

render.inject_css()


def sidebar() -> None:
    with st.sidebar:
        st.markdown("## ◑ jev lab")
        st.caption("Typed judgments over real market news and real X posts. "
                   "A demo of what a non-generative model is for.")
        st.divider()

        if have_key():
            st.success("API key found — live calls enabled", icon="✅")
        else:
            st.warning(f"No `{ENV_KEY}` — browsing stored judgments only", icon="⚠️")
            st.caption("Put the key in your shell or a `.env` file at the project root, then "
                       "restart. Everything still works read-only without it.")

        db = get_db()
        rows = store.coverage(db)
        stored = sum(r["judged"] for r in rows)
        st.metric("judgments stored", f"{stored}")
        if rows:
            with st.expander("by question set"):
                for r in rows:
                    st.markdown(
                        f"**`{r['qset']}`**  \n{r['judged']} items · {r['model']} · "
                        f"~{int(r['avg_latency_ms'] or 0)} ms · "
                        f"${(r['input_tokens'] or 0) / 1e6 * DEFAULTS['price_per_mtok']:.4f}")

        spend = session_cost()
        if spend["calls"]:
            st.metric("this session", f"${spend['tokens'] / 1e6 * DEFAULTS['price_per_mtok']:.5f}",
                      delta=f"{spend['calls']} live calls · {spend['tokens']:,} tokens",
                      delta_color="off")

        st.divider()
        st.caption(f"model alias `{DEFAULTS['model']}` · {DEFAULTS['workers']} workers · "
                   f"${DEFAULTS['price_per_mtok']}/M input tokens, no output billing")
        st.caption("Sample data is a frozen snapshot: 100 Benzinga stories and 100 public X "
                   "posts, committed to the repo. Nothing is fetched at runtime.")


def main() -> None:
    st.title("Typed judgments, not generated text")
    st.caption("Pick an item. See the facts the model gets and the questions it is asked — "
               "options and all. Press the button. Every number that comes back was typed before "
               "it was asked for.")

    # A segmented control rather than `st.tabs`: Streamlit renders EVERY tab's body on every
    # rerun, and a dataframe laid out inside a hidden tab measures zero width and comes back with
    # its columns collapsed. Rendering one section at a time also keeps each rerun cheap.
    page = st.segmented_control(
        "section", ["📰  News", "𝕏  X posts", "⚡  Batch", "📘  How jev works"],
        default="📰  News", key="nav", label_visibility="collapsed")
    st.write("")
    {"📰  News": news_tab.render_tab,
     "𝕏  X posts": x_tab.render_tab,
     "⚡  Batch": batch_tab.render_tab,
     "📘  How jev works": learn_tab.render_tab}.get(page, news_tab.render_tab)()

    # Drawn LAST although it appears first: `st.sidebar` writes into the sidebar whenever it is
    # called, and the running cost is only known once the body has made its calls. Rendering it
    # first would show every live call one rerun late.
    sidebar()


main()
