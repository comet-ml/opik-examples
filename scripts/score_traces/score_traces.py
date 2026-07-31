"""Score existing production traces in an Opik project and log feedback back.

Flow: time window -> search_traces -> for each trace x eval, resolve the variable
mapping and call metric.score(), collecting one list -> one batched
log_traces_feedback_scores. Stateless and trace-scoped (Stage 0).
"""

import datetime as dt
import logging
import os
from typing import Any

import opik
from opik.evaluation.metrics import GEval

from metrics import EVALS, Eval
from paths import MissingField, resolve_variables

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger("score-traces")

PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "score-traces-example")
WINDOW_HOURS = int(os.environ.get("EVAL_WINDOW_HOURS", "1"))
MAX_RESULTS = int(os.environ.get("EVAL_MAX_RESULTS", "1000"))


def window_filter(hours: int) -> str:
    """OQL filter selecting traces started within the last `hours` (UTC, ISO 8601)."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)
    return f'start_time >= "{since.strftime("%Y-%m-%dT%H:%M:%SZ")}"'


def geval_payload(kwargs: dict[str, Any]) -> str:
    """Compose resolved variables into one labeled string for a GEval judge.

    GEval.score() evaluates a single `output` string and ignores other kwargs
    (per the Opik docs), so a judge that must see multiple trace fields (e.g.
    the question AND the answer) gets them as labeled sections in one payload.
    """
    return "\n".join(f"{key.upper()}: {value}" for key, value in kwargs.items())


def trace_to_data(trace: Any) -> dict[str, Any]:
    """Normalize a trace object into {input, output, metadata} dicts (each defaulting to {})."""
    return {
        "input": getattr(trace, "input", None) or {},
        "output": getattr(trace, "output", None) or {},
        "metadata": getattr(trace, "metadata", None) or {},
    }


def score_trace(trace: Any, defs: list[Eval]) -> list[dict[str, Any]]:
    """Score one trace against every eval. Returns feedback-score dicts.

    A missing variable field or a failing/raising metric skips that one eval
    (logged) and never aborts the others or the run.
    """
    data = trace_to_data(trace)
    scores: list[dict[str, Any]] = []
    for ev in defs:
        try:
            kwargs = resolve_variables(data, ev.variables)
        except MissingField as exc:
            LOGGER.warning("trace %s: skip '%s' — %s", trace.id, ev.name, exc)
            continue
        try:
            if isinstance(ev.metric, GEval):
                result = ev.metric.score(output=geval_payload(kwargs))
            else:
                result = ev.metric.score(**kwargs)
        except Exception as exc:  # noqa: BLE001 — one bad eval must not kill the run
            LOGGER.warning("trace %s: eval '%s' raised: %s", trace.id, ev.name, exc)
            continue
        if getattr(result, "scoring_failed", False):
            LOGGER.warning("trace %s: eval '%s' reported scoring_failed", trace.id, ev.name)
            continue
        scores.append(
            {
                "id": trace.id,
                "name": ev.name,
                "value": result.value,
                "reason": result.reason,  # preserve the judge's explanation
            }
        )
    return scores


def main() -> None:
    dry_run = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))
    if dry_run:
        print(
            "DRY_RUN: set OPIK_API_KEY + OPIK_WORKSPACE to score a project. "
            f"Would score project '{PROJECT_NAME}' over the last {WINDOW_HOURS}h "
            f"with evals: {[e.name for e in EVALS]}."
        )
        return

    client = opik.Opik(project_name=PROJECT_NAME)
    traces = list(
        client.search_traces(
            project_name=PROJECT_NAME,
            filter_string=window_filter(WINDOW_HOURS),
            max_results=MAX_RESULTS,
        )
    )

    all_scores: list[dict[str, Any]] = []
    for trace in traces:
        all_scores.extend(score_trace(trace, EVALS))

    if all_scores:
        client.log_traces_feedback_scores(all_scores)  # SDK batches internally
    client.flush()

    print(
        f"Scored {len(traces)} traces x {len(EVALS)} evals -> "
        f"{len(all_scores)} scores logged to '{PROJECT_NAME}'."
    )
    if len(traces) >= MAX_RESULTS:
        LOGGER.warning(
            "Hit EVAL_MAX_RESULTS=%s — results may be truncated. "
            "Shorten EVAL_WINDOW_HOURS or raise EVAL_MAX_RESULTS.",
            MAX_RESULTS,
        )


if __name__ == "__main__":
    main()
