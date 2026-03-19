"""
Creates an Opik dashboard with an Experiment Leaderboard panel
from a YAML config file produced by run_experiments.py.

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

    Layout uses a 24-column grid. The leaderboard widget takes full width.

    Column terminology:
      predefined_columns  → standard fields  (e.g. 'dataset_id', 'trace_count')
      score_columns       → feedback scores  (e.g. 'feedback_scores.accuracy')
      metadata_columns    → experiment_config keys (e.g. 'config.model')
    """
    section_id = str(uuid.uuid4())
    widget_id = str(uuid.uuid4())

    # All non-score, non-metadata columns shown in the table
    # selectedColumns controls visibility for ALL column types:
    #   - predefined: filtered by checking against PREDEFINED_COLUMNS definitions
    #   - score cols: detected by parseScoreColumnId (feedback_scores.* / experiment_scores.*)
    #   - metadata:   detected by startsWith("metadata.")
    # All three must be present here or they won't render.
    all_selected = predefined_columns + score_columns + metadata_columns

    # columnsOrder only governs the ORDER of predefined columns in the table.
    predefined_order = predefined_columns

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
        "sections": [
            {
                "id": section_id,
                "title": "Leaderboard",
                "layout": [
                    {
                        "i": widget_id,
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
                        "id": widget_id,
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
        ],
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
    print("The leaderboard shows these experiments, ranked by", ranking_metric)
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
