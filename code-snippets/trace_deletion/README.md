# Delete Old Traces

A script to bulk-delete Opik traces older than N months for one or more projects.

## Requirements

- Python 3.9+
- `requests` library (`pip install requests`)
- Opik API credentials

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPIK_API_KEY` | Yes | — | Your Opik API key |
| `OPIK_WORKSPACE` | Yes | — | Workspace name |
| `OPIK_BASE_URL` | No | `https://www.comet.com` | Base URL for the Opik API |

## Usage

```bash
# Set environment variables, then run
python delete_old_traces.py --projects "my-project" --months 3

# Dry run (no deletions, just reports what would be deleted)
python delete_old_traces.py --projects "my-project" --dry-run
```

## Arguments

| Flag | Default | Description |
|---|---|---|
| `--projects` | `PROJECT_NAMES` in script | One or more project names to clean up |
| `--months` | `3` | Delete traces older than this many months |
| `--dry-run` | off | Preview deletions without actually deleting |

## Configuring Projects in the Script

Instead of passing `--projects` each time, edit the `PROJECT_NAMES` list near the bottom of the script:

```python
PROJECT_NAMES = [
    "my-production-project",
    "another-project",
]
```

Then run without `--projects`:

```bash
source ../../.env.dev && python delete_old_traces.py
```

## How It Works

1. For each project, fetches all trace IDs with a creation time before the cutoff date (paginated, 1000 traces per page).
2. Deletes traces in batches of 1000 via the Opik API, with a short delay between batches to avoid rate limiting.
3. Prints a summary of how many traces were deleted per project and in total.
