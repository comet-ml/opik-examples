# Opik Trace Manager

A CLI tool to inspect and delete [Opik](https://www.comet.com/site/products/opik/) traces by date range, tags, or TTL policies — across one project or your entire workspace.

## Prerequisites

- Python 3.10+
- `pip install requests`

## Environment Setup

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPIK_API_KEY` | Yes | — | Your Opik / Comet API key |
| `OPIK_WORKSPACE` | Yes | — | Workspace name |
| `OPIK_BASE_URL` | No | `https://www.comet.com` | API base URL (self-hosted installs) |

```bash
export OPIK_API_KEY=your-api-key
export OPIK_WORKSPACE=your-workspace
```

---

## Recommended Workflow

Always inspect before you delete.

### Step 1 — Inspect (count matching traces, no changes)

```bash
python manage_traces.py list --projects my-project --older-than-days 90
```

```
Resolving projects...
Opik Trace Inspector
  Workspace : my-workspace
  Filters   : before 2025-01-17

  my-project                                →    1,743 traces match

  ──────────────────────────────────────────────────────────
  Total: 1,743 traces across 1 project(s)
```

### Step 2 — Dry-run (preview batches, no changes)

```bash
python manage_traces.py delete --projects my-project --older-than-days 90 --dry-run
```

### Step 3 — Execute

```bash
# Interactive (prompts for confirmation)
python manage_traces.py delete --projects my-project --older-than-days 90

# Non-interactive (skip prompt — for cron/CI)
python manage_traces.py delete --projects my-project --older-than-days 90 --yes
```

---

## Command Reference

### `list` — count-only inspection

```
python manage_traces.py list [filter options]
```

Prints the number of matching traces per project. Makes one lightweight API call per project (reads the `total` field only — does not paginate through all traces). Safe to run at any time.

### `delete` — delete matching traces

```
python manage_traces.py delete [filter options] [--dry-run] [--yes]
```

| Flag | Description |
|---|---|
| `--dry-run` | Show what would be deleted, batch by batch. No API delete calls. |
| `--yes` | Skip the interactive confirmation prompt. |

### Shared filter options (work on both `list` and `delete`)

| Flag | Description |
|---|---|
| `--projects NAME [NAME ...]` | Projects to target. Omit to target **all** projects in the workspace. |
| `--config FILE` | Load settings from a JSON config file. CLI flags override config values. |
| `--older-than-days N` | Target traces older than N days. Mutually exclusive with `--before`. |
| `--before DATE` | Target traces created before this ISO 8601 date (e.g. `2025-01-31`). |
| `--after DATE` | Target traces created after this ISO 8601 date (lower bound). |
| `--tag TAG [TAG ...]` | Include only traces containing **all** of these tags. |
| `--exclude-tag TAG [TAG ...]` | Exclude traces containing **any** of these tags. |

---

## Config File

Use a config file when you want to script complex rules (e.g. per-tag TTL policies, multiple projects) without repeating long CLI flags.

```bash
python manage_traces.py list   --config config_example.json
python manage_traces.py delete --config config_example.json --dry-run
python manage_traces.py delete --config config_example.json --yes
```

CLI flags always override the config file.

### Config file format

**Option A — flat filters** (single deletion pass):

```json
{
  "projects": ["my-project", "another-project"],
  "filters": {
    "older_than_days": 90,
    "tags": [],
    "exclude_tags": []
  }
}
```

**Option B — TTL rules** (multiple passes, processed shortest-retention-first):

```json
{
  "projects": ["my-project"],
  "ttl_rules": [
    { "tags": ["sensitive", "PII"], "older_than_days": 30, "description": "Short retention for PII" },
    { "tags": ["internal"],         "older_than_days": 60 },
    { "tags": [],                   "older_than_days": 90, "description": "Default catch-all" }
  ]
}
```

When `ttl_rules` is used:
- Rules are sorted by `older_than_days` ascending (shortest retention = most aggressive = runs first).
- The rule with empty `"tags": []` is the catch-all — it automatically excludes all tags configured in prior rules so traces aren't double-counted.
- If both `filters` and `ttl_rules` are present, `ttl_rules` wins and a warning is printed.

See [`config_example.json`](config_example.json) for a fully annotated example.

---

## Common Recipes

### Delete traces older than 3 months in one project

```bash
python manage_traces.py delete --projects my-project --older-than-days 90 --yes
```

### Delete traces in a date window

```bash
python manage_traces.py delete \
  --projects my-project \
  --after 2024-06-01 --before 2024-12-31 \
  --dry-run
```

### Delete traces with a specific tag, older than 30 days

```bash
python manage_traces.py delete \
  --projects my-project \
  --tag sensitive \
  --older-than-days 30 \
  --yes
```

### Apply per-tag TTL rules across the entire workspace

```bash
# Omit --projects to target every project
python manage_traces.py delete --config config_example.json --yes
```

### Cron / scheduled deletion

```bash
# In a crontab or CI step — non-interactive, all workspace projects
OPIK_API_KEY=... OPIK_WORKSPACE=... \
  python manage_traces.py delete --config /path/to/ttl.json --yes
```

---

## How It Works

1. **Config validation** — if `--config` is provided, the file is validated before any network calls.
2. **Project resolution** — named projects are verified against the workspace; unknown names cause an early error with the list of available projects. If no projects are specified, all workspace projects are discovered automatically.
3. **Filter construction** — CLI flags and config are merged (`TraceFilter` dataclass). Filters are sent as query parameters to the Opik API.
4. **Trace collection** — paginated `GET /traces` calls (up to 1,000 per page). `list` uses a single lightweight call; `delete` paginates to collect all matching IDs.
5. **Batch deletion** — `POST /traces/delete` with up to 1,000 IDs per request, with a 0.2 s delay between batches to respect rate limits.

---

## Troubleshooting

**`ERROR: OPIK_API_KEY environment variable is not set.`**
Export the required environment variables before running.

**`ERROR: Project(s) not found in workspace: ['my-typo']`**
The script lists available projects — check the name spelling.

**`ERROR: No filter criteria specified.`**
At least one of `--older-than-days`, `--before`, `--after`, `--tag`, or `--exclude-tag` is required (or a `--config` file that specifies filters).

**HTTP 429 / rate limit errors**
The tool already applies a 0.2 s delay between delete batches. If you still hit limits, the `RATE_LIMIT_DELAY` constant at the top of `manage_traces.py` can be increased.
