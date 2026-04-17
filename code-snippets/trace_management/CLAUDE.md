# Opik Trace Manager — Agent Instructions

This tool inspects and deletes Opik traces by date range, tags, or TTL policies.
Script: `manage_traces.py` in this directory.

## Environment setup

```bash
export OPIK_API_KEY=your-api-key
export OPIK_WORKSPACE=your-workspace
# Optional:
export OPIK_BASE_URL=https://www.comet.com
```

## Safety rule — always inspect before deleting

```bash
# 1. Inspect (read-only, no changes)
python manage_traces.py list [filter flags]

# 2. Dry-run (preview batches, no changes)
python manage_traces.py delete [filter flags] --dry-run

# 3. Execute (interactive confirmation prompt)
python manage_traces.py delete [filter flags]

# 3b. Execute non-interactively (cron / CI)
python manage_traces.py delete [filter flags] --yes
```

## Filter flags (same on both `list` and `delete`)

| Flag | Example | Description |
|---|---|---|
| `--projects` | `--projects proj-a proj-b` | Target these projects. Omit = all workspace projects. |
| `--older-than-days` | `--older-than-days 90` | Traces older than N days. |
| `--before` | `--before 2025-01-31` | Traces created before this ISO 8601 date. |
| `--after` | `--after 2024-06-01` | Traces created after this date (lower bound). |
| `--tag` | `--tag sensitive PII` | Include only traces with ALL these tags. |
| `--exclude-tag` | `--exclude-tag keep` | Exclude traces with ANY of these tags. |
| `--config` | `--config ttl.json` | Load from JSON config file. CLI flags override. |

## Common commands

```bash
# Count traces older than 90 days in one project
python manage_traces.py list --projects my-project --older-than-days 90

# Delete traces with 'sensitive' tag older than 30 days (dry-run first)
python manage_traces.py delete --projects my-project --tag sensitive --older-than-days 30 --dry-run
python manage_traces.py delete --projects my-project --tag sensitive --older-than-days 30 --yes

# Delete traces in a date window
python manage_traces.py delete --projects my-project --after 2024-01-01 --before 2024-12-31 --yes

# Apply TTL config across all workspace projects
python manage_traces.py list   --config config_example.json
python manage_traces.py delete --config config_example.json --dry-run
python manage_traces.py delete --config config_example.json --yes
```

## Config file format

Two modes — use `filters` for a single pass, `ttl_rules` for per-tag retention:

```json
{
  "projects": ["my-project"],

  "filters": {
    "older_than_days": 90,
    "tags": [],
    "exclude_tags": []
  }
}
```

```json
{
  "projects": ["my-project"],
  "ttl_rules": [
    { "tags": ["sensitive", "PII"], "older_than_days": 30 },
    { "tags": ["internal"],         "older_than_days": 60 },
    { "tags": [],                   "older_than_days": 90 }
  ]
}
```

- `ttl_rules` are sorted shortest-retention-first automatically.
- Empty `"tags": []` is the catch-all rule (applied last, excludes all prior tags).
- If both `filters` and `ttl_rules` are present, `ttl_rules` wins.
- Config is validated before any network calls.

## Error reference

| Error | Fix |
|---|---|
| `OPIK_API_KEY environment variable is not set` | Export the env vars |
| `Project(s) not found in workspace` | Check spelling; script lists available projects |
| `No filter criteria specified` | Add `--older-than-days`, `--before`, `--tag`, or `--config` |
| `Config file is not valid JSON` | Fix syntax in the JSON file |
| `ttl_rules[N] is missing required field "older_than_days"` | Add `older_than_days` to each TTL rule |

## API notes

- Projects endpoint: `GET /opik/api/v1/private/projects` (paginated at 100/page)
- Traces endpoint: `GET /opik/api/v1/private/traces` (paginated at 1,000/page)
- Delete endpoint: `POST /opik/api/v1/private/traces/delete` (max 1,000 IDs per call)
- Rate limit delay: 0.2 s between delete batches (configurable via `RATE_LIMIT_DELAY` in script)
- Filters are AND-combined server-side
- `list` command uses a single size=1 request per project (reads `total` field only — fast)
