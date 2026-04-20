"""
Creates an Opik dashboard with an Experiment Leaderboard panel and
one bar-chart widget per feedback score metric, all from a YAML config
file produced by run_experiments.py.

Usage:
    source ../../.env.dev && python create_leaderboard_from_yaml.py
    source ../../.env.dev && python create_leaderboard_from_yaml.py --config my_config.yaml
    source ../../.env.dev && python create_leaderboard_from_yaml.py --replace  # overwrite existing
"""

import argparse
import os
import time
import uuid

import opik
import yaml


# ---------------------------------------------------------------------------
# Dashboard config builder
# ---------------------------------------------------------------------------

def _score_name(score_column_id: str) -> str:
    """Strip the 'feedback_scores.' prefix to get the raw metric name."""
    prefix = "feedback_scores."
    return score_column_id[len(prefix):] if score_column_id.startswith(prefix) else score_column_id


def _build_metric_chart_widgets(
    experiment_ids: list[str],
    score_columns: list[str],
) -> tuple[list[dict], list[dict]]:
    """
    Build metric chart widgets for a dashboard section.

    Layout (24-column grid):
      Row 0  — full-width radar chart showing all metrics at once
      Row 1+ — one bar-chart per metric, two per row

    Returns (widgets, layout) ready to embed in a dashboard section.
    """
    widgets: list[dict] = []
    layout: list[dict] = []

    RADAR_H = 6
    COLS_PER_ROW = 8
    WIDGET_W = 24 // COLS_PER_ROW   # 3
    WIDGET_H = 5      # was 10  → quarter area

    raw_names = [_score_name(col) for col in score_columns]

    # --- Radar chart (all metrics, full width) ---
    radar_id = str(uuid.uuid4())
    layout.append({
        "i": radar_id,
        "x": 0,
        "y": 0,
        "w": 6,
        "h": RADAR_H,
        "minW": 3,
        "minH": 3,
    })
    widgets.append({
        "id": radar_id,
        "title": "All Metrics — Radar",
        "type": "experiments_feedback_scores",
        "config": {
            "overrideDefaults": True,
            "dataSource": "select_experiments",
            "experimentIds": experiment_ids,
            "filters": [],
            # Empty list → show all scores; radar charts are designed for
            # comparing multiple dimensions simultaneously.
            "feedbackScores": raw_names,
            "chartType": "radar",
            "maxExperimentsCount": 50,
        },
    })

    # --- Individual bar charts (one per metric) ---
    for idx, raw_name in enumerate(raw_names):
        widget_id = str(uuid.uuid4())
        row = idx // COLS_PER_ROW
        col = idx % COLS_PER_ROW

        w = WIDGET_W   # uniform size; all widgets stay at their column position

        layout.append({
            "i": widget_id,
            "x": col * WIDGET_W,
            "y": RADAR_H + row * WIDGET_H,
            "w": w,
            "h": WIDGET_H,
            "minW": 3,
            "minH": 3,
        })
        widgets.append({
            "id": widget_id,
            "title": f"{raw_name.capitalize()} by Experiment",
            "type": "experiments_feedback_scores",
            "config": {
                # overrideDefaults=True → widget uses its own experimentIds, not
                # the dashboard-level selection.
                "overrideDefaults": True,
                "dataSource": "select_experiments",
                "experimentIds": experiment_ids,
                "filters": [],
                # Passing exactly one name pins the widget to its labelled metric.
                "feedbackScores": [raw_name],
                # Bar chart compares experiments side-by-side for a single metric.
                "chartType": "bar",
                "maxExperimentsCount": 50,
            },
        })

    return widgets, layout


def build_dashboard_config(
    experiment_ids: list[str],
    ranking_metric: str,
    ranking_direction: bool,
    predefined_columns: list[str],
    score_columns: list[str],
    metadata_columns: list[str],
) -> dict:
    """
    Returns the full DashboardState JSON that the Opik backend persists.

    Layout uses a 24-column grid.
    - Section 1 "Leaderboard"     — full-width leaderboard table
    - Section 2 "Metric Charts"   — one bar-chart widget per feedback score

    Column terminology:
      predefined_columns  → standard fields  (e.g. 'dataset_id', 'trace_count')
      score_columns       → feedback scores  (e.g. 'feedback_scores.accuracy')
      metadata_columns    → experiment_config keys (e.g. 'config.model')
    """
    leaderboard_section_id = str(uuid.uuid4())
    leaderboard_widget_id = str(uuid.uuid4())

    # All non-score, non-metadata columns shown in the table
    # selectedColumns controls visibility for ALL column types:
    #   - predefined: filtered by checking against PREDEFINED_COLUMNS definitions
    #   - score cols: detected by parseScoreColumnId (feedback_scores.* / experiment_scores.*)
    #   - metadata:   detected by startsWith("metadata.")
    # All three must be present here or they won't render.
    all_selected = predefined_columns + score_columns + metadata_columns

    # columnsOrder only governs the ORDER of predefined columns in the table.
    predefined_order = predefined_columns

    leaderboard_section = {
        "id": leaderboard_section_id,
        "title": "Leaderboard",
        "layout": [
            {
                "i": leaderboard_widget_id,
                "x": 0,
                "y": 0,
                "w": 24,   # full-width — grid is 24 columns
                "h": 14,
                "minW": 6,
                "minH": 6,
            }
        ],
        "widgets": [
            {
                "id": leaderboard_widget_id,
                "title": "Experiment Leaderboard",
                "type": "experiment_leaderboard",
                "config": {
                    # overrideDefaults=True means widget ignores dashboard-level
                    # experiment selection and uses its own experimentIds list.
                    "overrideDefaults": True,
                    "dataSource": "select_experiments",
                    "experimentIds": experiment_ids,
                    "filters": [],
                    # --- Ranking ---
                    "enableRanking": True,
                    "rankingMetric": ranking_metric,
                    # rankingDirection maps to sort `desc`:
                    #   True  → descending (higher is better, e.g. accuracy)
                    #   False → ascending  (lower is better, e.g. latency)
                    "rankingDirection": ranking_direction,
                    # --- Column visibility & order ---
                    # selectedColumns: ALL visible columns (predefined + scores + metadata).
                    # The widget dispatches each ID to the right renderer by prefix:
                    #   no prefix         → predefined column
                    #   feedback_scores.* → score column
                    #   metadata.*        → metadata column
                    "selectedColumns": all_selected,
                    # columnsOrder: ordering for predefined columns only.
                    "columnsOrder": predefined_order,
                    # scoresColumnsOrder: ordering for feedback_scores.* columns.
                    "scoresColumnsOrder": score_columns,
                    # metadataColumnsOrder: ordering for metadata.* columns.
                    "metadataColumnsOrder": metadata_columns,
                    "columnsWidth": {},
                    "maxRows": 50,
                    # Persist the sort state so the UI opens pre-sorted
                    "sorting": [
                        {"id": ranking_metric, "desc": ranking_direction}
                    ],
                },
            }
        ],
    }

    sections = [leaderboard_section]

    if score_columns:
        chart_widgets, chart_layout = _build_metric_chart_widgets(experiment_ids, score_columns)
        sections.append({
            "id": str(uuid.uuid4()),
            "title": "Metric Charts",
            "layout": chart_layout,
            "widgets": chart_widgets,
        })

    return {
        "version": 1,
        "lastModified": int(time.time() * 1000),
        "config": {
            "dateRange": {"preset": "last_30_days"},
            "projectIds": [],
            "experimentIds": experiment_ids,
            "experimentDataSource": "select_experiments",
            "experimentFilters": [],
            "maxExperimentsCount": 50,
        },
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_existing_dashboard(client, name: str) -> str | None:
    """Return the ID of the first dashboard matching `name`, or None."""
    page = client.dashboards.find_dashboards(name=name, size=10)
    if page and page.content:
        for d in page.content:
            if d.name == name:
                return d.id
    return None


def get_workspace() -> str:
    """Best-effort: derive workspace name from env or leave blank."""
    return os.environ.get("OPIK_WORKSPACE", "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(config_path: str, replace: bool) -> None:
    # -- Load YAML --
    print(f"[1/3] Loading config from '{config_path}' ...")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    experiment_ids: list[str] = [e["id"] for e in cfg["experiments"]]
    lb = cfg["leaderboard"]

    dashboard_name: str = lb["dashboard_name"]
    description: str = lb.get("description", "")
    ranking_metric: str = lb["ranking_metric"]
    ranking_direction: bool = bool(lb["ranking_direction"])

    cols = lb["columns"]
    predefined_columns: list[str] = cols.get("predefined", [])
    score_columns: list[str] = cols.get("scores", [])
    metadata_columns: list[str] = cols.get("metadata", [])

    print(f"  Dashboard name : {dashboard_name}")
    print(f"  Experiments    : {len(experiment_ids)}")
    print(f"  Ranking metric : {ranking_metric} ({'↓ higher=better' if ranking_direction else '↑ lower=better'})")
    print(f"  Score columns  : {score_columns}")
    print(f"  Metadata cols  : {metadata_columns}")

    # -- Connect --
    # Use opik.Opik() so it reads OPIK_API_KEY, OPIK_WORKSPACE, OPIK_URL_OVERRIDE
    # etc. from the environment automatically, then grab its pre-configured
    # REST client for the dashboards API.
    print("[2/3] Connecting to Opik ...")
    opik_client = opik.Opik()
    client = opik_client.rest_client
    workspace = get_workspace()

    # -- Check for existing dashboard --
    existing_id = find_existing_dashboard(client, dashboard_name)
    if existing_id and not replace:
        print(f"\nDashboard '{dashboard_name}' already exists (id={existing_id}).")
        print("Re-run with --replace to overwrite it.")
        return

    # -- Build config --
    dashboard_config = build_dashboard_config(
        experiment_ids=experiment_ids,
        ranking_metric=ranking_metric,
        ranking_direction=ranking_direction,
        predefined_columns=predefined_columns,
        score_columns=score_columns,
        metadata_columns=metadata_columns,
    )

    # -- Create or replace --
    print("[3/3] Creating dashboard ...")

    if existing_id and replace:
        print(f"  Deleting existing dashboard {existing_id} ...")
        client.dashboards.delete_dashboard(dashboard_id=existing_id)

    dashboard = client.dashboards.create_dashboard(
        name=dashboard_name,
        description=description,
        type="experiments",
        scope="workspace",
        config=dashboard_config,
    )

    # -- Report --
    slug = getattr(dashboard, "slug", None) or dashboard_name.lower().replace(" ", "-")
    url = (
        f"https://www.comet.com/{workspace}/dashboards/{slug}"
        if workspace
        else f"(dashboard id: {dashboard.id})"
    )

    print()
    print("Dashboard created successfully!")
    print(f"  ID   : {dashboard.id}")
    print(f"  URL  : {url}")
    print()
    print("Sections:")
    print("  1. Leaderboard — ranked by", ranking_metric)
    print(f"  2. Metric Charts — radar (all metrics) + {len(score_columns)} bar-chart widget(s):", score_columns)
    print()
    print("Experiments:")
    for exp in cfg["experiments"]:
        print(f"  - {exp['name']} ({exp['model']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create an Opik leaderboard dashboard from a YAML config."
    )
    parser.add_argument(
        "--config",
        default="leaderboard_config.yaml",
        help="Path to the YAML config file (default: leaderboard_config.yaml)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete and recreate the dashboard if it already exists",
    )
    args = parser.parse_args()
    main(args.config, args.replace)
