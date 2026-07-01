"""
Oversight Team — Governance Metrics Extraction from Opik
=========================================================
Runs once per day at ~02:00, after the business unit's batch (01:00) is complete.

For every project in the workspace:
  1. Enumerate all projects via find_projects().
  2. Skip projects with no governance-tagged traces (cheap probe call).
  3. For each remaining project, call get_project_metrics() for each metric type,
     filtered to governance-tagged traces. Opik / ClickHouse aggregates server-side.
  4. Build a structured payload and POST to the oversight reporting endpoint.

Usage:
    python data_governance_team.py

Required env vars:
    OPIK_API_KEY
    OPIK_WORKSPACE
    OPIK_URL_OVERRIDE        (optional, for self-hosted deployments)
    OVERSIGHT_INGEST_URL     (optional, URL of your reporting/ingestion endpoint)

Docs:
    https://www.comet.com/docs/opik/python-sdk-reference/rest_api/clients/projects.html#opik.rest_api.projects.client.ProjectsClient.get_project_metrics
"""

import json
import os
from datetime import UTC, datetime, timedelta

from opik.rest_api.client import OpikApi
from opik.rest_api.core.request_options import RequestOptions
from opik.rest_api.types.trace_filter_public import TraceFilterPublic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_BASE_URL = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")
GOVERNANCE_TAG = "governance"  # must match the tag used in agent_tracing.py

# No Opik credentials -> describe the extraction and exit without calling the Opik API.
DRY_RUN = not (os.environ.get("OPIK_API_KEY") and WORKSPACE)

_now = datetime.now(UTC)

# Metric types to extract. Each maps to one get_project_metrics() call.
# See the full list of available values in the SDK docs linked above.
METRIC_TYPES = [
    "FEEDBACK_SCORES",  # average per named feedback score
]

# Interval for aggregation. Choose one: "HOURLY" | "DAILY" | "WEEKLY" | "TOTAL"
INTERVAL = "DAILY"

# Look-back window for the extraction.
LOOKBACK_DAYS = 30


def build_client() -> OpikApi:
    return OpikApi(
        api_key=os.environ["OPIK_API_KEY"],
        workspace_name=WORKSPACE,
        base_url=OPIK_BASE_URL,
    )


# ---------------------------------------------------------------------------
# Project enumeration
# ---------------------------------------------------------------------------


def list_all_projects(client: OpikApi) -> list[dict]:
    """Page through find_projects() and return [{"id": ..., "name": ...}, ...]."""
    projects = []
    page = 1
    while True:
        resp = client.projects.find_projects(page=page, size=50)
        if not resp or not resp.content:
            break
        projects.extend({"id": p.id, "name": p.name} for p in resp.content)
        if len(resp.content) < 50:
            break
        page += 1
    return projects


# ---------------------------------------------------------------------------
# Filters
#
# TraceFilterPublic is the typed filter object accepted by get_project_metrics().
# Multiple filters in the list are AND-ed together.
#
# Tag filter:
#   TraceFilterPublic(field="tags", operator="contains", value="governance")
#
# Metadata filters (optional, for governance dimension breakdowns):
#   TraceFilterPublic(field="metadata", key="env",           operator="=", value="prod")
#   TraceFilterPublic(field="metadata", key="risk_tier",     operator="=", value="high")
#   TraceFilterPublic(field="metadata", key="business_unit", operator="=", value="retail")
# ---------------------------------------------------------------------------


def _governance_filters(metadata_slice: dict[str, str] | None = None) -> list[TraceFilterPublic]:
    """
    Build the filter list for a governance extraction.
    Always includes the governance tag filter; optionally AND-s metadata key/value pairs.
    """
    filters = [
        TraceFilterPublic(field="tags", operator="contains", value=GOVERNANCE_TAG),
    ]
    for key, value in (metadata_slice or {}).items():
        filters.append(TraceFilterPublic(field="metadata", key=key, operator="=", value=value))
    return filters


# ---------------------------------------------------------------------------
# Metadata slices (optional governance breakdowns)
#
# By default the extraction runs once per project with only the governance tag
# filter applied (the "all" slice). To break down metrics by a governance
# dimension, add metadata key/value pairs here. Each entry produces a separate
# get_project_metrics() call and its own block in the output payload.
#
# Examples:
#   {"env": "prod"}
#   {"risk_tier": "high"}
#   {"env": "prod", "risk_tier": "high"}   # compound — both filters AND-ed
#   {"business_unit": "retail"}
#
# Leave as an empty list for a single unfiltered extraction.
# ---------------------------------------------------------------------------

METADATA_SLICES: list[dict[str, str]] = [
    # {"env": "prod"},
    # {"risk_tier": "high"},
]


# ---------------------------------------------------------------------------
# Metrics extraction
# ---------------------------------------------------------------------------


def fetch_metrics_for_project(
    client: OpikApi,
    project_id: str,
    metadata_slice: dict[str, str] | None = None,
) -> dict:
    """
    Call get_project_metrics() for each metric type in METRIC_TYPES.

    Returns { metric_type: [{"name": score_name, "data": [{time, value}, ...]}, ...] }

    Each call returns a ProjectMetricResponsePublic:
      response.results  — list of ResultsNumberPublic, one per named score
        result.name     — score name (e.g. "composite_risk_score")
        result.data     — list of DataPointNumberPublic (time, value) data points
    """
    trace_filters = _governance_filters(metadata_slice)
    interval_start = _now - timedelta(days=LOOKBACK_DAYS)
    req_opts: RequestOptions = {"timeout_in_seconds": 60}
    metrics: dict = {}

    for metric_type in METRIC_TYPES:
        response = client.projects.get_project_metrics(
            id=project_id,
            metric_type=metric_type,
            interval=INTERVAL,
            interval_start=interval_start,
            interval_end=_now,
            trace_filters=trace_filters,
            request_options=req_opts,
        )

        if not response or not response.results:
            metrics[metric_type] = []
            continue

        metrics[metric_type] = [
            {
                "name": result.name,
                "data": [
                    {"time": point.time.isoformat(), "value": point.value}
                    for point in (result.data or [])
                    if point.value is not None
                ],
            }
            for result in response.results
        ]

    return metrics


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_extraction() -> list[dict]:
    print(f"\n{'=' * 60}")
    print(f"Governance Metrics Extraction  {_now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Workspace : {WORKSPACE}")
    print(f"Tag       : {GOVERNANCE_TAG}")
    print(f"Interval  : {INTERVAL}  |  Look-back: {LOOKBACK_DAYS} days")
    print(f"{'=' * 60}\n")

    client = build_client()
    projects = list_all_projects(client)
    payloads = []

    print(f"Projects found: {len(projects)}\n")

    for project in projects:
        print(f"Project: {project['name']}")

        # Cheap probe: TRACE_COUNT/TOTAL with only the governance tag filter.
        # Skips the full extraction for projects with no governance-tagged traces.
        probe = client.projects.get_project_metrics(
            id=project["id"],
            metric_type="TRACE_COUNT",
            interval="TOTAL",
            interval_start=_now - timedelta(days=LOOKBACK_DAYS),
            interval_end=_now,
            trace_filters=_governance_filters(),
            request_options={"timeout_in_seconds": 60},
        )
        probe_has_data = any(point.value for result in (probe.results or []) for point in (result.data or []))
        if not probe_has_data:
            print("  No governance-tagged traces — skipping.\n")
            continue

        # Build slices: always run the unfiltered "all" slice, then any extras.
        slices_to_run: list[tuple[str, dict[str, str]]] = [("all", {})]
        for metadata_slice in METADATA_SLICES:
            label = "&".join(f"{k}={v}" for k, v in sorted(metadata_slice.items()))
            slices_to_run.append((label, metadata_slice))

        sliced_metrics: dict[str, dict] = {}
        for label, metadata_slice in slices_to_run:
            sliced_metrics[label] = {
                "slice_filter": metadata_slice,
                "metrics": fetch_metrics_for_project(client, project["id"], metadata_slice),
            }

        payload = {
            "schema_version": "2.0",
            "extracted_at": _now.isoformat(),
            "workspace": WORKSPACE,
            "project_id": project["id"],
            "project_name": project["name"],
            "governance_tag": GOVERNANCE_TAG,
            "slices": sliced_metrics,
        }
        payloads.append(payload)

        print(f"  Slices computed: {list(sliced_metrics.keys())}")
        print()

    _push_to_reporting_endpoint(payloads)

    out = f"governance_extract_{_now.strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w") as f:
        json.dump(payloads, f, indent=2, default=str)
    print(f"Payloads written to: {out}")

    return payloads


def _push_to_reporting_endpoint(payloads: list[dict]) -> None:
    endpoint = os.environ.get("OVERSIGHT_INGEST_URL")
    if not endpoint:
        print(f"[STUB] OVERSIGHT_INGEST_URL not set — skipping POST ({len(payloads)} payload(s))")
        return
    print(f"[STUB] Would POST {len(payloads)} payload(s) to {endpoint}")
    # Uncomment to enable:
    # import requests
    # requests.post(
    #     endpoint,
    #     json=payloads,
    #     headers={"Authorization": f"Bearer {os.environ['OVERSIGHT_API_TOKEN']}"},
    # ).raise_for_status()


if __name__ == "__main__":
    if DRY_RUN:
        print(
            "[DRY RUN] Opik creds not set — would extract governance metrics across "
            f"all projects for '{GOVERNANCE_TAG}'-tagged traces and build the reporting payload."
        )
        raise SystemExit(0)

    run_extraction()
