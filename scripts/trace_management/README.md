# Opik Trace Manager

A CLI tool to inspect and delete [Opik](https://www.comet.com/site/products/opik/) traces by date range, tags, or TTL policies — across one project or your entire workspace.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — this folder is a `uv` project; run `uv sync`

Built on the [`opik` Python SDK](https://pypi.org/project/opik/), so pagination,
rate-limit backoff and retries are the SDK's rather than hand-rolled here.

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
uv run python manage_traces.py list --projects my-project --older-than-days 90
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
uv run python manage_traces.py delete --projects my-project --older-than-days 90 --dry-run
```

### Step 3 — Execute

```bash
# Interactive (prompts for confirmation)
uv run python manage_traces.py delete --projects my-project --older-than-days 90

# Non-interactive (skip prompt — for cron/CI)
uv run python manage_traces.py delete --projects my-project --older-than-days 90 --yes
```

---

## Command Reference

### `list` — count-only inspection

```
uv run python manage_traces.py list [filter options]
```

Prints the number of matching traces per project. Makes one lightweight API call per project (reads the `total` field only — does not paginate through all traces). Safe to run at any time.

### `delete` — delete matching traces

```
uv run python manage_traces.py delete [filter options] [--dry-run] [--yes]
```

| Flag | Description |
|---|---|
| `--dry-run` | Show the count, the date window actually matched, and the batch plan. No API delete calls. |
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
| `--time-field {ingestion,start_time}` | Which clock the date bounds use. Default `ingestion`. See [Which date is "older than"?](#which-date-is-older-than) |

---

## Which date is "older than"?

A trace carries two timestamps, and for retention they can disagree:

| Clock | What it is | Flag |
|---|---|---|
| **`ingestion`** | When the backend received the trace, read from the timestamp embedded in its id. Assigned server-side. Answers *"how long have we held this data?"* | default |
| **`start_time`** | The trace's own timestamp, set by whatever logged it — the time shown in the Opik UI. Answers *"how old is the activity this describes?"* | `--time-field start_time` |

For traces logged as the work happens the two agree to within milliseconds. **They
diverge for backfilled or replayed data**: a trace imported today carrying last year's
`start_time` is a year old on one clock and seconds old on the other.

**The default is `ingestion`, and for a retention policy it is usually the one you
want.** A commitment like *"we do not keep customer data longer than 90 days"* is a
claim about custody, measured from when you received the data — so a trace imported
today should be kept for 90 more days regardless of the date it carries.

It also matters that **`start_time` is supplied by whatever wrote the trace**, and is
accepted as given:

```python
# Perfectly acceptable to the API — the trace is created now, but claims to be old.
{"name": "...", "start_time": "2020-01-01T00:00:00.000Z", ...}
```

A retention control keyed on a field the data producer sets is not really a control: a
skewed clock or a bad actor stamping `start_time` far in the future keeps data past its
deletion date, and the sweep still reports success. Ingestion time cannot be shifted
that way, which is what makes it the auditable choice.

Choose `--time-field start_time` when the policy really is about the age of the
activity — or when working with backfilled fixtures, which is why
`test_manage_traces.py` forces it.

Whichever you pick, `--dry-run` prints the window it actually matched and names the
clock, so you can check it against the UI before deleting anything:

```
  my-project — 1,743 traces (before 2025-01-17)
      window       : 2024-10-02 06:23 → 2025-01-16 20:11 UTC (by ingestion)
      plan         : 9 delete batch(es) of 200
```

## Config File

Use a config file when you want to script complex rules (e.g. per-tag TTL policies, multiple projects) without repeating long CLI flags.

```bash
uv run python manage_traces.py list   --config config_example.json
uv run python manage_traces.py delete --config config_example.json --dry-run
uv run python manage_traces.py delete --config config_example.json --yes
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

`time_field` may be set inside `filters`, or at the top level to apply to every pass
(including every TTL rule). `--time-field` on the CLI overrides both.

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
- **Within one rule, `tags` is matched as OR** — `{"tags": ["sensitive", "PII"]}` becomes one pass per tag, so a trace carrying *either* tag is targeted. Note this is the opposite of the `--tag` flag, which requires *all* listed tags on the same trace.
- Because each pass is counted separately, a trace carrying two listed tags is counted once per pass. **Counts reported for a TTL config are an upper bound**; the deletion total is exact, since a later pass no longer finds what an earlier one removed.
- The rule with empty `"tags": []` is the catch-all — it automatically excludes all tags configured in prior rules so traces aren't double-counted.
- If both `filters` and `ttl_rules` are present, `ttl_rules` wins and a warning is printed.

See [`config_example.json`](config_example.json) for a fully annotated example.

---

## Common Recipes

### Delete traces older than 3 months in one project

```bash
uv run python manage_traces.py delete --projects my-project --older-than-days 90 --yes
```

### Delete traces in a date window

```bash
uv run python manage_traces.py delete \
  --projects my-project \
  --after 2024-06-01 --before 2024-12-31 \
  --dry-run
```

### Delete traces with a specific tag, older than 30 days

```bash
uv run python manage_traces.py delete \
  --projects my-project \
  --tag sensitive \
  --older-than-days 30 \
  --yes
```

### Apply per-tag TTL rules across the entire workspace

```bash
# Omit --projects to target every project
uv run python manage_traces.py delete --config config_example.json --yes
```

### Cron / scheduled deletion

The tool exits **0** on success and **1** on any failure — bad config, or an API error
while counting or deleting — so a scheduler can alert on it.

```bash
# Daily 02:00 — bounded, non-overlapping, fails loudly.
0 2 * * * /usr/bin/flock -n /tmp/opik-ttl.lock \
  timeout 2h uv run --project /opt/trace_management \
  python manage_traces.py delete --config /etc/opik/ttl.json --yes \
  >> /var/log/opik-ttl.log 2>&1 \
  || echo "opik retention FAILED" | mail -s 'opik retention' ops@example.com
```

- `flock -n` — skip this run if the previous one is still going, instead of piling up.
- `timeout` — cap total runtime. The tool waits out rate limits rather than failing, so
  a very large first sweep can run long; this bounds it and the next run picks up where
  it left off.
- `|| …` — the tool's non-zero exit is what makes failures visible.

On Kubernetes, a `CronJob` with `concurrencyPolicy: Forbid` and
`activeDeadlineSeconds` gives the same two guarantees natively.

Running `list` on the same schedule is a cheap canary — it is read-only, and its counts
should stay flat once retention is keeping up.

---

## How It Works

1. **Config validation** — if `--config` is provided, the file is validated before any network calls.
2. **Project resolution** — named projects are verified against the workspace; unknown names cause an early error with the list of available projects. If no projects are specified, all workspace projects are discovered automatically.
3. **Filter construction** — CLI flags and config are merged (`TraceFilter` dataclass). Date bounds become `from_time` / `to_time`; tag predicates become server-side filters.
4. **Counting** (`list`, and the `--dry-run` / confirmation preview) — one `size=1` request per project per filter, reading only the `total`. Nothing is enumerated, so a preview is fast at any volume.
5. **Deletion** (`delete`) — read a page of matching traces, delete that page, repeat until nothing matches.

Step 5 is the important one. Deleting what was just read is what makes the loop
terminate: the result set genuinely shrinks, so the next read returns the next
traces rather than the same ones. Two consequences:

- **Memory is bounded** by one page, not by the total number of matches.
- **Progress is durable.** If a run is interrupted, everything already deleted stays
  deleted and a rerun resumes naturally — it just asks again what still matches.

Reads carry only `id` and `start_time`; trace bodies, feedback scores, comments and
attachments are excluded server-side, so a sweep does not transfer payloads it will
discard. A guard aborts the loop if a page comes back unchanged after a delete
(which would otherwise spin), and marks the run failed.

> **Why not offset pagination?** Because the offsets go stale. Asking for "page 2"
> after deleting page 1 skips a page's worth of traces, since everything shifted up.
> This tool therefore never uses page numbers for deletion; the non-mutating paths
> use the API's `last_retrieved_id` cursor.

---

## Tests

```bash
# Offline, no credentials, no network, milliseconds. Covers the delete loop's
# pagination: termination above one page, exactly-once deletion, page boundaries,
# and the no-progress guard.
uv run python test_pagination.py
```

`test_manage_traces.py` is a separate **live** end-to-end script: it seeds real traces
into a temporary project in your workspace and walks every CLI scenario, pausing before
each deletion. It needs credentials and it writes data — read its docstring first.

> Anything touching how pages are walked should get a case in `test_pagination.py`. The
> live script seeds only ~70 traces, so it cannot see multi-page behaviour at all.

## Troubleshooting

**`ERROR: OPIK_API_KEY environment variable is not set.`**
Export the required environment variables before running.

**`ERROR: Project(s) not found in workspace: ['my-typo']`**
The script lists available projects — check the name spelling.

**`ERROR: No filter criteria specified.`**
At least one of `--older-than-days`, `--before`, `--after`, `--tag`, or `--exclude-tag` is required (or a `--config` file that specifies filters).

**HTTP 429 / rate limit errors**
Handled automatically — every API call waits out a 429 for the duration the server's
`Retry-After` header specifies, then retries. A large first sweep may therefore take a
while; bound it with `timeout` (see the cron recipe above) rather than interrupting it,
since progress is durable.

**A run appears to stall**
Check the log for `Rate limited (HTTP 429)`. If instead you see `no progress deleting
from …`, deletes are being accepted but not taking effect — usually a permissions
problem — and the tool has stopped rather than spinning. It exits non-zero in that case.

---

## API notes

All calls go through the `opik` SDK's REST client rather than raw HTTP.

- Projects: `find_projects` (paginated at 100/page)
- Counting: `get_traces_by_project` with `size=1` — reads the `total` field only, fast
- Reading for deletion: `search_traces` (streaming, cursor-based via `last_retrieved_id`),
  `SEARCH_PAGE_SIZE` = 1,000 per page
- Deleting: `delete_traces`, `DELETE_BATCH_SIZE` = 200 IDs per call. The API's hard cap is
  1,000; 200 is a deliberate margin, and both constants are at the top of the script
- Reads exclude trace bodies and aggregates (`input`, `output`, `metadata`,
  `feedback_scores`, `comments`, `usage`, …) plus `strip_attachments`, since only `id` and
  `start_time` are used
- Date bounds (`--before` / `--after` / `--older-than-days`) become `to_time` / `from_time`
  by default, which bound the trace id; under `--time-field start_time` they become
  `start_time` filter predicates instead. Both bounds always share one clock — an earlier
  revision mixed them, filtering `--before` on the id and `--after` on `start_time`
- Tag predicates are AND-combined server-side
- Rate limits (HTTP 429) are waited out per the server's `Retry-After`
