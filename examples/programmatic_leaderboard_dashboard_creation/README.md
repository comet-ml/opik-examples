# Opik Experiment Leaderboard — Programmatic Setup

> **Demo scripts** for creating an Experiment Leaderboard dashboard in Opik entirely via the REST API, with no UI interaction required. Copy this folder and adapt the dataset, experiment configs, and scoring metrics to your own use case.

This directory demonstrates how to create an **Experiment Leaderboard dashboard** in Opik entirely via the REST API, with no UI interaction required.

---

## Files

| File | Purpose |
|------|---------|
| `run_experiments.py` | Runs two experiments against a shared dataset and writes a YAML config |
| `create_leaderboard_from_yaml.py` | Reads the YAML and creates the leaderboard dashboard via the REST API |
| `leaderboard_config.yaml` | Generated config — experiment IDs, score names, column definitions |

---

## Quick Start

All scripts must be run from the script directory with the environment sourced from the repo root.

### Step 1 — Run experiments and generate config

```bash
python run_experiments.py
```

This creates a dataset (`leaderboard-demo`), runs two experiments with different model configurations, scores each item on `accuracy`, `relevance`, and `conciseness`, and writes `leaderboard_config.yaml`.

### Step 2 — Create the leaderboard dashboard

```bash
python create_leaderboard_from_yaml.py
```

The script reads the YAML and calls `POST /opik/api/v1/private/dashboards` to create a dashboard with the leaderboard widget pre-configured.

If the dashboard already exists, you'll be prompted to re-run with `--replace`:

```bash
python create_leaderboard_from_yaml.py --replace
```

### Options

```bash
# Use a different config file
python create_leaderboard_from_yaml.py --config my_config.yaml

# Overwrite an existing dashboard with the same name
python create_leaderboard_from_yaml.py --replace
```

---

## The Generated Config (`leaderboard_config.yaml`)

```yaml
dataset:
  id: <uuid>
  name: leaderboard-demo

experiments:
  - id: <uuid>
    name: "leaderboard-demo: gpt-4o"
    model: gpt-4o
    url: <experiment url>
  - id: <uuid>
    name: "leaderboard-demo: gpt-4o-mini"
    model: gpt-4o-mini
    url: <experiment url>

leaderboard:
  dashboard_name: Model Evaluation Leaderboard
  description: Ranks experiments by accuracy score
  ranking_metric: feedback_scores.accuracy
  ranking_direction: true     # true = higher is better (descending)
  columns:
    predefined:               # built-in experiment fields
      - dataset_id
      - created_at
      - duration.p50
      - trace_count
      - total_estimated_cost_avg
    scores:                   # feedback score columns
      - feedback_scores.accuracy
      - feedback_scores.conciseness
      - feedback_scores.relevance
    metadata:                 # experiment_config keys
      - metadata.model
      - metadata.temperature
      - metadata.max_tokens
      - metadata.strategy
```

Edit this file directly to change which experiments, metrics, or columns appear in the leaderboard before running `create_leaderboard_from_yaml.py`.

---

## REST API Overview

The leaderboard is part of Opik's **Dashboards API**. All endpoints are under:

```
https://www.comet.com/opik/api/v1/private/dashboards
```

### Authentication

```bash
-H "Authorization: Bearer $OPIK_API_KEY"
-H "Comet-Workspace: $OPIK_WORKSPACE"
-H "Content-Type: application/json"
```

### Create a dashboard

```
POST /opik/api/v1/private/dashboards
```

```json
{
  "name": "My Leaderboard",
  "description": "Ranks experiments by accuracy",
  "type": "experiments",
  "scope": "workspace",
  "config": { ... }
}
```

**`type`**: `experiments` (for leaderboard/comparison dashboards) or `multi_project` (for production monitoring dashboards).

**`scope`**: `workspace` (visible to everyone in the workspace) or `insights`.

### List dashboards

```
GET /opik/api/v1/private/dashboards?name=My+Leaderboard&size=10
```

### Update a dashboard

```
PATCH /opik/api/v1/private/dashboards/{dashboardId}
```

### Delete a dashboard

```
DELETE /opik/api/v1/private/dashboards/{dashboardId}
```

---

## Dashboard Config Structure

The `config` field is a JSON blob that defines the full dashboard state.

```json
{
  "version": 1,
  "lastModified": 1234567890000,
  "config": {
    "dateRange": { "preset": "last_30_days" },
    "projectIds": [],
    "experimentIds": ["exp-id-1", "exp-id-2"],
    "experimentDataSource": "select_experiments",
    "experimentFilters": [],
    "maxExperimentsCount": 50
  },
  "sections": [
    {
      "id": "<uuid>",
      "title": "Leaderboard",
      "layout": [
        { "i": "<widget-uuid>", "x": 0, "y": 0, "w": 24, "h": 14, "minW": 6, "minH": 6 }
      ],
      "widgets": [ { ... } ]
    }
  ]
}
```

The grid is **24 columns wide**. Set `w: 24` for a full-width widget.

---

## Leaderboard Widget Config

The widget `type` is `experiment_leaderboard`. Its `config` controls which experiments load, how ranking works, and which columns appear.

```json
{
  "id": "<uuid>",
  "title": "Experiment Leaderboard",
  "type": "experiment_leaderboard",
  "config": {
    "overrideDefaults": true,
    "dataSource": "select_experiments",
    "experimentIds": ["exp-id-1", "exp-id-2"],
    "filters": [],
    "enableRanking": true,
    "rankingMetric": "feedback_scores.accuracy",
    "rankingDirection": true,
    "selectedColumns": ["dataset_id", "created_at", "feedback_scores.accuracy", "metadata.model"],
    "columnsOrder": ["dataset_id", "created_at"],
    "scoresColumnsOrder": ["feedback_scores.accuracy", "feedback_scores.relevance"],
    "metadataColumnsOrder": ["metadata.model"],
    "columnsWidth": {},
    "maxRows": 50,
    "sorting": [{ "id": "feedback_scores.accuracy", "desc": true }]
  }
}
```

### Key config fields

| Field | Type | Description |
|-------|------|-------------|
| `overrideDefaults` | bool | `true` = widget uses its own `experimentIds`, ignoring the dashboard-level selection |
| `dataSource` | string | `select_experiments` (explicit IDs) or `filter_and_group` (dynamic filter) |
| `experimentIds` | string[] | Experiment IDs to show. Used when `dataSource = select_experiments` |
| `filters` | array | Experiment filter rules. Used when `dataSource = filter_and_group` |
| `enableRanking` | bool | Show rank column and trophy icon on the ranking metric |
| `rankingMetric` | string | Column ID to rank by (e.g. `feedback_scores.accuracy`) |
| `rankingDirection` | bool | `true` = descending (higher is better). `false` = ascending (lower is better) |
| `selectedColumns` | string[] | **All** visible column IDs — predefined, scores, and metadata combined |
| `columnsOrder` | string[] | Display order for predefined columns only |
| `scoresColumnsOrder` | string[] | Display order for score columns |
| `metadataColumnsOrder` | string[] | Display order for metadata columns |
| `maxRows` | int | Max experiments to display (1–200) |
| `sorting` | array | Persisted sort state: `[{ "id": "<column-id>", "desc": true }]` |

### Column ID formats

The widget identifies column type by ID prefix:

| Column type | ID format | Example |
|-------------|-----------|---------|
| Predefined (built-in fields) | bare name | `dataset_id`, `trace_count`, `duration.p50` |
| Feedback score | `feedback_scores.<name>` | `feedback_scores.accuracy` |
| Experiment score | `experiment_scores.<name>` | `experiment_scores.overall` |
| Experiment config/metadata | `metadata.<key>` | `metadata.model`, `metadata.temperature` |

> **Important:** All columns that should be visible — including score and metadata columns — must be present in `selectedColumns`. The widget uses this list as the source of truth for visibility. `scoresColumnsOrder` and `metadataColumnsOrder` control only the display order of columns that are already in `selectedColumns`.

### Predefined column IDs

| ID | Description |
|----|-------------|
| `dataset_id` | Evaluation suite (dataset) the experiment ran against |
| `created_at` | Creation timestamp |
| `created_by` | Creator username |
| `trace_count` | Number of traces |
| `duration.p50` | Median trace duration |
| `duration.p90` | p90 trace duration |
| `duration.p99` | p99 trace duration |
| `total_estimated_cost` | Total cost across all traces |
| `total_estimated_cost_avg` | Average cost per trace |
| `tags` | Experiment tags |
| `pass_rate` | Pass rate across all scored items |

### Data source modes

**`select_experiments`** — pin specific experiments by ID:
```json
{
  "dataSource": "select_experiments",
  "experimentIds": ["id-1", "id-2", "id-3"]
}
```

**`filter_and_group`** — dynamically load experiments matching a filter (up to `maxRows`):
```json
{
  "dataSource": "filter_and_group",
  "experimentIds": [],
  "filters": [
    { "field": "dataset_name", "operator": "contains", "value": "prod-eval" }
  ]
}
```

---

## Python SDK

The same operations are available through the Opik Python SDK without constructing raw HTTP requests.

```python
import opik

# The high-level client reads OPIK_API_KEY, OPIK_WORKSPACE, OPIK_URL_OVERRIDE from env.
# .rest_client exposes the full generated REST API client.
client = opik.Opik().rest_client

# Create
dashboard = client.dashboards.create_dashboard(
    name="My Leaderboard",
    type="experiments",
    scope="workspace",
    config={ ... },
)

# List (filter by name)
page = client.dashboards.find_dashboards(name="My Leaderboard", size=10)

# Update
client.dashboards.update_dashboard(dashboard_id=dashboard.id, config={ ... })

# Delete
client.dashboards.delete_dashboard(dashboard_id=dashboard.id)
```
