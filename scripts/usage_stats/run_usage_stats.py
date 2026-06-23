"""
Opik Usage Stats — time-series metrics per project, rolled up to daily and
monthly DataFrames with matplotlib charts.

Requires:
    uv sync   (or: pip install opik pandas matplotlib)

Environment variables:
    OPIK_API_KEY       — your Opik API key (required)
    OPIK_WORKSPACE     — workspace name (optional, uses default)
    OPIK_URL_OVERRIDE  — only needed for self-hosted deployments
"""

import datetime
import os

import matplotlib.pyplot as plt
import opik
import pandas as pd

# ---------------------------------------------------------------------------
# 1.  Authenticate
# ---------------------------------------------------------------------------
client = opik.Opik(
    api_key=os.environ["OPIK_API_KEY"],
    workspace=os.environ.get("OPIK_WORKSPACE"),
)

WORKSPACE = os.environ.get("OPIK_WORKSPACE", "default")

# ---------------------------------------------------------------------------
# 2.  Analysis window (last 30 days by default — adjust as needed)
# ---------------------------------------------------------------------------
now = datetime.datetime.now(datetime.UTC)
INTERVAL_START = now - datetime.timedelta(days=30)
INTERVAL_END = now

# Metrics to pull for each project
METRIC_TYPES = [
    "TRACE_COUNT",
    "THREAD_COUNT",
    "SPAN_COUNT",
    "TOKEN_USAGE",
    "COST",
]

# ---------------------------------------------------------------------------
# 3.  Fetch all projects
# ---------------------------------------------------------------------------
projects_resp = client.rest_client.projects.find_projects()
projects = projects_resp.content or []

print(f"Found {len(projects)} project(s) in workspace '{WORKSPACE}'")

# ---------------------------------------------------------------------------
# 4.  Collect daily time-series into a tidy DataFrame
# ---------------------------------------------------------------------------
records = []

for project in projects:
    if not project.id:
        continue
    for metric in METRIC_TYPES:
        response = client.rest_client.projects.get_project_metrics(
            id=project.id,
            metric_type=metric,
            interval="DAILY",
            interval_start=INTERVAL_START,
            interval_end=INTERVAL_END,
        )
        for result in response.results or []:
            for dp in result.data or []:
                records.append(
                    {
                        "workspace": WORKSPACE,
                        "project_id": project.id,
                        "project": project.name,
                        "metric": metric,
                        "series": result.name,  # e.g. model name for TOKEN_USAGE
                        "date": dp.time.date(),
                        "value": dp.value or 0.0,
                    }
                )

df_daily = pd.DataFrame(records)

if df_daily.empty:
    print("No metric data returned for the selected window. Exiting.")
    raise SystemExit(0)

df_daily["date"] = pd.to_datetime(df_daily["date"])

# ---------------------------------------------------------------------------
# 5.  Roll up to monthly
# ---------------------------------------------------------------------------
def rollup(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    return (
        df.groupby(["workspace", "project", "metric", "series",
                    pd.Grouper(key="date", freq=freq)])
        ["value"]
        .sum()
        .reset_index()
    )

df_monthly = rollup(df_daily, "ME")

# ---------------------------------------------------------------------------
# 6.  Print summary tables
# ---------------------------------------------------------------------------
def print_summary(df: pd.DataFrame, label: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print("=" * 70)
    pivot = (
        df.groupby(["workspace", "project", "metric"])["value"]
        .sum()
        .reset_index()
        .pivot_table(index=["workspace", "project"], columns="metric",
                     values="value", aggfunc="sum", fill_value=0)
    )
    print(pivot.to_string())

print_summary(df_daily,   "DAILY TOTALS (last 30 days)")
print_summary(df_monthly, "MONTHLY TOTALS")

# ---------------------------------------------------------------------------
# 7.  Charts — stacked bar for TRACE_COUNT, THREAD_COUNT, SPAN_COUNT only.
#     TOKEN_USAGE and COST are available in the DataFrames / CSVs but not charted.
# ---------------------------------------------------------------------------
COUNT_METRICS = {"TRACE_COUNT", "THREAD_COUNT", "SPAN_COUNT"}

metrics_present = [m for m in df_daily["metric"].unique() if m in COUNT_METRICS]
project_names   = df_daily["project"].unique().tolist()
color_map       = plt.colormaps["tab10"].resampled(max(len(project_names), 1))
project_colors  = {p: color_map(i) for i, p in enumerate(project_names)}

def _pivot_for_plot(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Return a date-indexed DataFrame with one column per project."""
    subset = df[df["metric"] == metric].groupby(["date", "project"])["value"].sum().unstack(fill_value=0)
    subset.index = pd.to_datetime(subset.index)
    return subset.sort_index()


fig, axes = plt.subplots(
    nrows=len(metrics_present),
    ncols=2,
    figsize=(16, 4 * len(metrics_present)),
    squeeze=False,
)
fig.suptitle(
    f"Opik workspace: {WORKSPACE}\n{INTERVAL_START.date()} → {INTERVAL_END.date()}",
    fontsize=13, fontweight="bold",
)

for row, metric in enumerate(metrics_present):
    # Left: daily stacked bar
    ax_bar = axes[row][0]
    pivot = _pivot_for_plot(df_daily, metric)

    if pivot.empty:
        ax_bar.set_visible(False)
    else:
        colors = [project_colors[p] for p in pivot.columns if p in project_colors]
        x = range(len(pivot))
        bottom = pd.Series([0.0] * len(pivot), index=pivot.index)
        for project, color in zip(pivot.columns, colors, strict=False):
            ax_bar.bar(x, pivot[project].values, bottom=bottom.values,
                       color=color, width=0.8, label=project)
            bottom += pivot[project]
        tick_labels = [d.strftime("%b %d") for d in pivot.index]
        step = max(1, len(tick_labels) // 8)
        ax_bar.set_xticks(list(x)[::step])
        ax_bar.set_xticklabels(tick_labels[::step], rotation=30, ha="right")
        ax_bar.set_title(f"{metric} — Daily", fontsize=10)
        ax_bar.set_ylabel("count")
        ax_bar.grid(True, alpha=0.3)
        if len(project_names) > 1:
            handles, labels = ax_bar.get_legend_handles_labels()
            ax_bar.legend(handles[:len(project_names)], labels[:len(project_names)],
                          fontsize=7, loc="upper left")

    # Right: cumulative line
    ax_cum = axes[row][1]
    if pivot.empty:
        ax_cum.set_visible(False)
    else:
        cum = pivot.cumsum()
        x_dates = list(range(len(cum)))
        for project, color in zip(cum.columns, colors, strict=False):
            ax_cum.plot(x_dates, cum[project].values,
                        color=color, linewidth=1.8, label=project)
        ax_cum.fill_between(x_dates, cum.sum(axis=1).values, alpha=0.08, color="grey")
        ax_cum.set_xticks(x_dates[::step])
        ax_cum.set_xticklabels(tick_labels[::step], rotation=30, ha="right")
        ax_cum.set_title(f"{metric} — Cumulative", fontsize=10)
        ax_cum.set_ylabel("cumulative count")
        ax_cum.grid(True, alpha=0.3)
        if len(project_names) > 1:
            handles, labels = ax_cum.get_legend_handles_labels()
            ax_cum.legend(handles[:len(project_names)], labels[:len(project_names)],
                          fontsize=7, loc="upper left")

plt.tight_layout()
plt.savefig("opik_usage_stats.png", dpi=150, bbox_inches="tight")
print("\nChart saved → opik_usage_stats.png")
plt.show()

# ---------------------------------------------------------------------------
# 8.  Export DataFrames to CSV (optional)
# ---------------------------------------------------------------------------
df_daily.to_csv("opik_stats_daily.csv", index=False)
df_monthly.to_csv("opik_stats_monthly.csv", index=False)
print("CSVs saved → opik_stats_daily.csv, opik_stats_monthly.csv")