"""
Opik Usage Stats — collect temporal + snapshot usage metrics for one Opik
workspace via the SDK, then render a self-contained HTML report plus CSVs.

Demonstrates two complementary Opik SDK collection methods:
  * rest_client.projects.get_project_metrics  — daily time series
  * rest_client.projects.get_project_stats    — current per-project snapshot

For cross-platform use-case growth & adoption reporting (Opik + EM + MPM), use
cometx: https://github.com/comet-ml/cometx/blob/main/README.md#growth-report

Requires:
    uv sync   (or: pip install opik pandas)

Environment variables:
    OPIK_API_KEY       — your Opik API key (required)
    OPIK_WORKSPACE     — workspace name (optional, uses default)
    OPIK_URL_OVERRIDE  — only needed for self-hosted deployments
"""

from __future__ import annotations

import datetime
import os

import opik
import pandas as pd

import report

# --- Analysis window: bounds the temporal charts only. Adjust as needed. ----
WINDOW_DAYS = 30

METRIC_TYPES = ["TRACE_COUNT", "THREAD_COUNT", "SPAN_COUNT", "TOKEN_USAGE", "COST"]

_DAILY_COLUMNS = ["workspace", "project_id", "project", "metric", "series", "date", "value"]
_SUMMARY_COLUMNS = ["project", "metric", "value"]


def fetch_daily(client, workspace, projects, start, end) -> pd.DataFrame:
    """Per-project daily time series via get_project_metrics."""
    records = []
    for project in projects:
        if not project.id:
            continue
        for metric in METRIC_TYPES:
            resp = client.rest_client.projects.get_project_metrics(
                id=project.id,
                metric_type=metric,
                interval="DAILY",
                interval_start=start,
                interval_end=end,
            )
            for result in resp.results or []:
                for dp in result.data or []:
                    records.append(
                        {
                            "workspace": workspace,
                            "project_id": project.id,
                            "project": project.name,
                            "metric": metric,
                            "series": result.name or "",
                            "date": dp.time.date(),
                            "value": dp.value or 0.0,
                        }
                    )
    df = pd.DataFrame(records, columns=_DAILY_COLUMNS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_summary(client, projects) -> pd.DataFrame:
    """Current per-project snapshot via get_project_stats (paginated)."""
    name_by_id = {p.id: p.name for p in projects if getattr(p, "id", None)}
    rows = []
    page = 1
    while True:
        resp = client.rest_client.projects.get_project_stats(page=page, size=100)
        items = resp.content or []
        for item in items:
            project = name_by_id.get(getattr(item, "project_id", None), "unknown")
            usage = getattr(item, "usage", None) or {}
            tokens_total = sum(float(v) for v in usage.values()) if usage else 0.0
            cost = getattr(item, "total_estimated_cost", None)
            if cost is None:
                cost = getattr(item, "total_estimated_cost_sum", None)
            values = {
                "TRACE_COUNT": getattr(item, "trace_count", 0) or 0,
                "THREAD_COUNT": getattr(item, "thread_count", 0) or 0,
                "TOKENS_TOTAL": tokens_total,
                "TOTAL_COST": cost or 0.0,
                "GUARDRAILS_FAILED_COUNT": getattr(item, "guardrails_failed_count", 0) or 0,
            }
            for metric, value in values.items():
                rows.append({"project": project, "metric": metric, "value": float(value)})
        if len(items) < 100:
            break
        page += 1
    return pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)


def rollup_monthly(df_daily: pd.DataFrame) -> pd.DataFrame:
    if df_daily.empty:
        return df_daily.copy()
    return (
        df_daily.groupby(
            ["workspace", "project", "metric", "series", pd.Grouper(key="date", freq="ME")]
        )["value"]
        .sum()
        .reset_index()
    )


def print_summary(df_daily: pd.DataFrame) -> None:
    if df_daily.empty:
        print("(no temporal data)")
        return
    pivot = (
        df_daily.groupby(["project", "metric"])["value"]
        .sum()
        .reset_index()
        .pivot_table(index="project", columns="metric", values="value", fill_value=0)
    )
    print("\n" + "=" * 70)
    print("  DAILY TOTALS (last 30 days)")
    print("=" * 70)
    print(pivot.to_string())


def main() -> None:
    client = opik.Opik(
        api_key=os.environ["OPIK_API_KEY"],
        workspace=os.environ.get("OPIK_WORKSPACE"),
    )
    workspace = os.environ.get("OPIK_WORKSPACE", "default")

    now = datetime.datetime.now(datetime.UTC)
    start = now - datetime.timedelta(days=WINDOW_DAYS)

    projects = client.rest_client.projects.find_projects(size=1000).content or []
    print(f"Found {len(projects)} project(s) in workspace '{workspace}'")

    df_daily = fetch_daily(client, workspace, projects, start, now)
    df_summary = fetch_summary(client, projects)

    if df_daily.empty and df_summary.empty:
        print("No usage data returned for the selected window. Exiting.")
        return

    df_monthly = rollup_monthly(df_daily)
    print_summary(df_daily)

    df_daily.to_csv("stats_daily.csv", index=False)
    df_monthly.to_csv("stats_monthly.csv", index=False)
    df_summary.to_csv("stats_summary.csv", index=False)

    report.write_report(
        "report.html",
        workspace=workspace,
        window_start=start.date(),
        window_end=now.date(),
        generated=now,
        df_daily=df_daily,
        df_summary=df_summary,
    )

    print("\nReport saved → report.html")
    print("CSVs saved   → stats_daily.csv, stats_monthly.csv, stats_summary.csv")


if __name__ == "__main__":
    main()
