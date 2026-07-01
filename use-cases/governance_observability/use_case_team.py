"""
Business Unit — Retrospective Metrics Batch (T+1)
==================================================
Runs once per day at ~01:00, after the previous day's agent runs are complete.

For every governance-tagged trace from yesterday:
  1. Read the scores already on the trace (written by the agent inline and by
     online evaluation rules configured in the Opik UI).
  2. Derive composite business metrics from those scores using the formulas
     defined below.
  3. Write the derived scores back to the same trace.

Online evaluation rules are configured directly in the Opik web app
(Project → Automation Rules) and do not need to be managed from this script.

Usage:
    python use_case_team.py

Required env vars:
    OPIK_API_KEY
    OPIK_WORKSPACE
    OPIK_PROJECT_NAME   (optional, defaults to "governance-data-demo")
    OPIK_URL_OVERRIDE   (optional, for self-hosted deployments)

Docs:
    https://www.comet.com/docs/opik/tracing/annotate_traces
"""

import json
import os
from datetime import UTC, datetime, timedelta

from opik.rest_api.client import OpikApi
from opik.rest_api.types.feedback_score_source import FeedbackScoreSource

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WORKSPACE = os.environ.get("OPIK_WORKSPACE")
PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "governance-data-demo")
OPIK_BASE_URL = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")
GOVERNANCE_TAG = "governance"

# No Opik credentials -> describe the batch and exit without calling the Opik API.
DRY_RUN = not (os.environ.get("OPIK_API_KEY") and WORKSPACE)


def build_client() -> OpikApi:
    return OpikApi(
        api_key=os.environ["OPIK_API_KEY"],
        workspace_name=WORKSPACE,
        base_url=OPIK_BASE_URL,
    )


def get_project_id(client: OpikApi) -> str:
    response = client.projects.find_projects(name=PROJECT_NAME, page=1, size=1)
    if not response or not response.content:
        raise ValueError(f"Project '{PROJECT_NAME}' not found in workspace '{WORKSPACE}'")
    return response.content[0].id


# ---------------------------------------------------------------------------
# Composite metric formulas
#
# Inputs are the scores already on each trace:
#   - "regulatory_compliance"  written by the LLM-judge online rule
#   - "hallucination_rate"     written by the agent inline
#   - "response_quality"       written by the agent inline
#   - "cost_usd"               written by the agent inline
#
# Derived scores written back:
#   - "composite_risk_score"   weighted combination of upstream scores
#   - "oversight_risk_flag"    binary flag: 1.0 when composite_risk < threshold
#   - "cost_per_quality_unit"  cost efficiency ratio
#
# Adapt these formulas to match your organisation's business rules.
# ---------------------------------------------------------------------------

RISK_THRESHOLD = 0.75


def derive_composite_risk_score(scores: dict[str, float]) -> float | None:
    """Weighted composite. Requires regulatory_compliance and hallucination_rate."""
    required = {"regulatory_compliance", "hallucination_rate"}
    if not required.issubset(scores.keys()):
        return None
    return round(
        0.5 * scores["regulatory_compliance"]
        + 0.3 * (1.0 - scores["hallucination_rate"])
        + 0.2 * scores.get("response_quality", 0.8),
        4,
    )


def derive_oversight_risk_flag(composite_risk: float | None) -> float | None:
    """1.0 when composite_risk falls below the threshold, otherwise 0.0."""
    if composite_risk is None:
        return None
    return 1.0 if composite_risk < RISK_THRESHOLD else 0.0


def derive_cost_per_quality_unit(scores: dict[str, float]) -> float | None:
    """Cost in USD divided by response quality. Returns None when either score is absent."""
    cost = scores.get("cost_usd")
    quality = scores.get("response_quality")
    if cost is None or quality is None or quality == 0:
        return None
    return round(cost / quality, 6)


# ---------------------------------------------------------------------------
# Batch job
# ---------------------------------------------------------------------------


def run_retrospective_batch(client: OpikApi, project_id: str) -> None:
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    from_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    to_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"Date range : {from_time.date()} 00:00 → 23:59 UTC")

    tag_filter = json.dumps([{"field": "tags", "operator": "contains", "value": GOVERNANCE_TAG}])

    page, page_size = 1, 100
    total_processed = 0
    total_scored = 0

    while True:
        response = client.traces.get_traces_by_project(
            project_id=project_id,
            page=page,
            size=page_size,
            filters=tag_filter,
            from_time=from_time,
            to_time=to_time,
        )

        if not response or not response.content:
            break

        for trace in response.content:
            total_processed += 1

            existing: dict[str, float] = {
                fs.name: fs.value for fs in (trace.feedback_scores or []) if fs.name and fs.value is not None
            }

            composite_risk = derive_composite_risk_score(existing)
            risk_flag = derive_oversight_risk_flag(composite_risk)
            cost_per_quality = derive_cost_per_quality_unit(existing)

            derived = [
                s
                for s in [
                    composite_risk is not None
                    and {
                        "name": "composite_risk_score",
                        "value": composite_risk,
                        "reason": "0.5×compliance + 0.3×(1−hallucination) + 0.2×quality",
                    },
                    risk_flag is not None
                    and {
                        "name": "oversight_risk_flag",
                        "value": risk_flag,
                        "reason": f"1.0 = composite_risk_score < {RISK_THRESHOLD}",
                    },
                    cost_per_quality is not None
                    and {
                        "name": "cost_per_quality_unit",
                        "value": cost_per_quality,
                        "reason": "cost_usd / response_quality",
                    },
                ]
                if s
            ]

            if not derived:
                continue

            for score in derived:
                client.traces.add_trace_feedback_score(
                    id=trace.id,
                    name=score["name"],
                    value=score["value"],
                    source=FeedbackScoreSource.SDK,
                    reason=score["reason"],
                )

            total_scored += 1

        if len(response.content) < page_size:
            break
        page += 1

    print(f"Processed  : {total_processed}")
    print(f"Scored     : {total_scored}")
    print(f"Skipped    : {total_processed - total_scored}  (missing upstream scores)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if DRY_RUN:
        print(
            "[DRY RUN] Opik creds not set — would derive composite governance scores "
            f"for yesterday's '{GOVERNANCE_TAG}'-tagged traces in project '{PROJECT_NAME}'."
        )
        raise SystemExit(0)

    print(f"\nProject  : {PROJECT_NAME}")
    print(f"Workspace: {WORKSPACE}\n")

    client = build_client()
    project_id = get_project_id(client)

    run_retrospective_batch(client, project_id)
