#!/usr/bin/env python3
"""jevlab/jev/client.py — credentials, one call per judgment, a pool for many, and the cost line.

**One judgment is one HTTP call** carrying the state and *every* question in the set. The questions
are evaluated against the same state in parallel, server-side, so asking ten questions costs
barely more than asking one — which is why a question set is a bundle and not ten calls.

**Failures are per item, never per run.** `judge_many` returns a result object per item carrying
either the answers or the error, so one malformed story cannot take down a hundred-item pass.

**Credentials** come from `TYPESAFE_API_KEY`, in the environment or in a `.env` file beside the
project. There is no other source; this demo deliberately depends on exactly one key.

Answers come back as plain dicts — `{"type": "choice", "choice": …, "probabilities": {…},
"confidence": …}` — so they can be stored as JSON without the SDK on the other side.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:                       # noqa: BLE001 — never let dotenv's absence block a run
    pass

DEFAULTS: Dict[str, Any] = {
    # The API exposes ALIASES, not versions (`jev-latest`, `jev-preview`); asking for a concrete
    # "jev-1.13" is a 400. So the alias is what we request, and `resolved_model` records the
    # concrete version the response names — judgments are stored under THAT, so an upgrade starts
    # a new row set instead of silently mixing two models under one label.
    "model": "jev-latest",
    "workers": 8,               # parallel requests; the published account ceiling is 1,200/min
    "timeout": 60.0,
    "max_retries": 3,
    "price_per_mtok": 0.042,    # input only — jev bills no output tokens
}

ENV_KEY = "TYPESAFE_API_KEY"


class JevError(RuntimeError):
    """Raised when a judgment cannot be made (no credentials, API error, bad answer)."""


def resolve_key(api_key: Optional[str] = None) -> str:
    """The API key, from the argument or the environment. Raises `JevError` with what to do."""
    key = api_key or os.getenv(ENV_KEY)
    if not key:
        raise JevError(
            f"No {ENV_KEY}. Put it in your shell (`export {ENV_KEY}=…`) or in a `.env` file at "
            f"the project root, then restart the app. Keys: https://typesafe.ai")
    return key


def have_key() -> bool:
    """True when a live call is possible. The UI uses this to decide what to offer."""
    return bool(os.getenv(ENV_KEY))


@dataclass
class Judgment:
    """One item's result: `answers` or `error`, never both. `key` is the caller's own handle."""

    key: Any
    answers: Optional[Dict[str, Dict[str, Any]]] = None
    error: Optional[str] = None
    input_tokens: int = 0
    latency_ms: int = 0
    model: str = ""

    @property
    def ok(self) -> bool:
        return self.answers is not None


class JevClient:
    """A thread-safe wrapper over `typesafe_sdk.TypeSafeClient`."""

    def __init__(self, *, model: Optional[str] = None, api_key: Optional[str] = None,
                 workers: Optional[int] = None, log: Optional[Callable[[str], None]] = None):
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        self.opts = dict(DEFAULTS)
        self.model = model or str(self.opts["model"])
        self.workers = int(workers or self.opts["workers"])
        self.log = log or (lambda _m: None)
        self._client = TypeSafeClient(
            api_key=resolve_key(api_key), model=self.model,
            timeout=float(self.opts["timeout"]),
            retry=RetryPolicy(max_retries=int(self.opts["max_retries"])))
        self._lock = threading.Lock()
        self.input_tokens = 0
        self.resolved_model: Optional[str] = None

    # ---------------------------------------------------------------- one
    def _call(self, state: Any, questions: Mapping[str, Any]) -> Tuple[Dict[str, Any], int, str]:
        """(answers, this call's input tokens, the model that answered)."""
        from typesafe_sdk import TypeSafeAPIError
        try:
            response = self._client.system_one(state, dict(questions))
        except TypeSafeAPIError as e:
            raise JevError(f"jev {getattr(e, 'status_code', '')}: {e}".strip()) from e
        except Exception as e:          # noqa: BLE001 — transport, validation, anything
            raise JevError(f"jev call failed: {e}") from e
        tokens = int(getattr(getattr(response, "usage", None), "input_tokens", 0) or 0)
        model = getattr(response, "model", None)
        with self._lock:
            self.input_tokens += tokens
            self.resolved_model = self.resolved_model or model
        return ({qid: plain(answer) for qid, answer in response.answers.items()},
                tokens, model or self.model)

    def judge(self, state: Any, questions: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Answers for one state, as plain dicts. Raises `JevError` on failure."""
        return self._call(state, questions)[0]

    def judge_one(self, key: Any, state: Any, questions: Mapping[str, Any]) -> Judgment:
        """`judge`, but timed and wrapped — an error becomes a `Judgment`, not an exception.

        The token count comes from THIS call's own usage, not from a before/after read of the
        running total: under `judge_many` eight threads share that counter, and differencing it
        would charge each item for whatever its neighbours happened to spend meanwhile."""
        started = time.perf_counter()
        try:
            answers, tokens, model = self._call(state, questions)
        except JevError as e:
            return Judgment(key=key, error=str(e),
                            latency_ms=int((time.perf_counter() - started) * 1000))
        return Judgment(key=key, answers=answers, input_tokens=tokens,
                        latency_ms=int((time.perf_counter() - started) * 1000), model=model)

    # ---------------------------------------------------------------- many
    def judge_many(self, items: Sequence[Tuple[Any, Any]], questions: Mapping[str, Any], *,
                   on_result: Optional[Callable[[Judgment], None]] = None) -> List[Judgment]:
        """`items` is [(key, state), …]. One `Judgment` per item, in the SAME ORDER.

        Pooled over `workers`. A failing item carries its error instead of raising.

        `on_result` fires as each item lands — **on the worker thread that produced it**, not the
        caller's. Anything it touches must be thread-safe, and a UI framework with thread-local
        state (Streamlit, for one) will refuse the call. `jevlab/ui/batch_tab.py` drives its
        progress bar by chunking instead."""
        results: List[Judgment] = [Judgment(key=k) for k, _s in items]
        if not items:
            return results

        def run(index: int) -> None:
            key, state = items[index]
            results[index] = self.judge_one(key, state, questions)
            if on_result:
                on_result(results[index])

        with ThreadPoolExecutor(max_workers=max(1, self.workers)) as pool:
            list(pool.map(run, range(len(items))))
        # `stored_model` is only known once a call has succeeded; stamp the whole batch with it.
        for r in results:
            if r.ok and not r.model:
                r.model = self.stored_model
        failed = sum(1 for r in results if not r.ok)
        self.log(f"jev: {len(results) - failed}/{len(results)} judged by {self.stored_model} · "
                 f"{self.input_tokens:,} input tokens ≈ ${self.cost:.4f}"
                 + (f" · {failed} failed" if failed else ""))
        return results

    @property
    def stored_model(self) -> str:
        """What judgments are KEYED by: the concrete version the API named, else the alias asked
        for (the alias only survives here when every call failed)."""
        return self.resolved_model or self.model

    @property
    def cost(self) -> float:
        """Dollars so far. Input tokens only — jev bills no output."""
        return self.input_tokens / 1_000_000 * float(self.opts["price_per_mtok"])


def plain(answer: Any) -> Dict[str, Any]:
    """An SDK answer -> a JSON-able dict, whichever primitive it is.

    Mapping keys are forced to `str`. A Score's `probabilities` and `legend` come back keyed by
    the integer level, and JSON has no integer keys — so a cached answer read back from the
    database would be keyed by `"3"` while a fresh one is keyed by `3`, and any lookup written
    for one would silently miss on the other. Normalising here means live and cached answers are
    the same shape everywhere downstream."""
    out: Dict[str, Any] = {"type": getattr(answer, "type", None)}
    for field_name in ("choice", "score", "noul", "confidence", "probabilities", "legend"):
        value = getattr(answer, field_name, None)
        if value is not None:
            out[field_name] = ({str(k): v for k, v in value.items()}
                               if isinstance(value, Mapping) else value)
    return out


def truncate(text: Any, limit: int) -> str:
    """Clip a state field. jev's documented weakness is a bloated state, not a short one."""
    text = " ".join(str(text or "").split())
    return text[:limit] if limit else text
