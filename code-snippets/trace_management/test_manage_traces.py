#!/usr/bin/env python3
"""
End-to-end test script for manage_traces.py.

Creates a set of test traces across different dates and tags in a temporary
project, then walks through each CLI scenario. The script pauses before any
deletion so you can inspect the project in the Opik UI first.

Scenarios covered:
  1. list  — count all traces in the project
  2. list  — count by tag
  3. list  — count by date range (--after / --before)
  4. delete --dry-run  — preview by tag
  5. delete --dry-run  — preview with date range
  6. delete --dry-run  — preview with TTL config file
  7. delete --yes      — delete by tag
  8. delete --yes      — delete by date range
  9. delete --yes      — delete remaining via TTL config

Usage:
    python test_manage_traces.py [--project PROJECT_NAME] [--skip-seed] [--skip-pause]

Requires environment variables:
    OPIK_API_KEY, OPIK_WORKSPACE, OPIK_BASE_URL (optional)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_PROJECT = "trace-manager-test"
DEFAULT_BASE_URL = "https://www.comet.com"

# Trace distribution to seed
# Each entry: (days_ago, tags)
TRACE_SEEDS = (
    # Old traces — various tags
    *[(95, ["sensitive"])        for _ in range(10)],
    *[(95, ["PII"])              for _ in range(10)],
    *[(95, ["internal"])         for _ in range(10)],
    *[(95, [])                   for _ in range(10)],  # untagged, old
    # Medium-age traces
    *[(45, ["sensitive"])        for _ in range(5)],
    *[(45, ["internal"])         for _ in range(5)],
    *[(45, [])                   for _ in range(5)],
    # Recent traces — should survive most filters
    *[(5,  ["sensitive"])        for _ in range(5)],
    *[(5,  [])                   for _ in range(5)],
)

# Mirrors config_example.json TTL rules
TTL_RULES = [
    {"tags": ["sensitive", "PII"], "older_than_days": 30},
    {"tags": ["internal"],         "older_than_days": 60},
    {"tags": [],                   "older_than_days": 90, "description": "Default catch-all"},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_env() -> dict:
    api_key = os.environ.get("OPIK_API_KEY")
    workspace = os.environ.get("OPIK_WORKSPACE")
    base_url = os.environ.get("OPIK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    if not api_key:
        print("ERROR: OPIK_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)
    if not workspace:
        print("ERROR: OPIK_WORKSPACE is not set.", file=sys.stderr)
        sys.exit(1)

    return {"api_key": api_key, "workspace": workspace, "base_url": base_url}


def make_headers(env: dict) -> dict:
    return {
        "Authorization": f"Bearer {env['api_key']}",
        "Comet-Workspace": env["workspace"],
        "Content-Type": "application/json",
    }


def seed_traces(env: dict, project_name: str) -> None:
    """Create test traces directly via the Opik REST API."""
    url = f"{env['base_url']}/opik/api/v1/private/traces/batch"
    now = datetime.now(tz=timezone.utc)
    batch = []

    for days_ago, tags in TRACE_SEEDS:
        start = now - timedelta(days=days_ago)
        end = start + timedelta(seconds=1)
        batch.append({
            "project_name": project_name,
            "name": f"test-trace-{days_ago}d-{'_'.join(tags) or 'untagged'}",
            "start_time": start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "end_time":   end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "tags": tags,
        })

    # API accepts batch creation
    resp = requests.post(url, headers=make_headers(env), json={"traces": batch})
    if not resp.ok:
        print(f"ERROR seeding traces: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    print(f"  Seeded {len(batch)} traces into project '{project_name}'")
    print()


def count_traces(env: dict, project_name: str) -> int:
    url = f"{env['base_url']}/opik/api/v1/private/traces"
    resp = requests.get(url, headers=make_headers(env),
                        params={"project_name": project_name, "page": 1, "size": 1})
    resp.raise_for_status()
    return resp.json().get("total", 0)


def pause(msg: str, skip: bool) -> None:
    if skip:
        print(f"  [pause skipped] {msg}")
        return
    print()
    print(f"  >>> {msg}")
    input("      Press Enter to continue...")
    print()


def section(title: str) -> None:
    bar = "─" * 60
    print()
    print(bar)
    print(f"  {title}")
    print(bar)


def run(args: list[str], label: str) -> None:
    """Run manage_traces.py with the given args and print the command."""
    cmd = ["python", "manage_traces.py"] + args
    print(f"\n  $ {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, cwd=os.path.dirname(__file__))
    if result.returncode not in (0, 1):
        print(f"\n  WARNING: '{label}' exited with code {result.returncode}")


def write_temp_config(project_name: str, rules: list[dict]) -> str:
    path = os.path.join(os.path.dirname(__file__), "_test_ttl_config.json")
    cfg = {"projects": [project_name], "ttl_rules": rules}
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    return path


def write_tag_only_config(project_name: str) -> str:
    """Config with tags only — no date filter. Targets ALL traces with these tags."""
    path = os.path.join(os.path.dirname(__file__), "_test_tag_only_config.json")
    cfg = {
        "projects": [project_name],
        "filters": {
            "tags": ["internal"],
            "exclude_tags": ["sensitive"]
        }
    }
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="End-to-end test for manage_traces.py")
    p.add_argument("--project", default=DEFAULT_PROJECT,
                   help=f"Project name to use (default: {DEFAULT_PROJECT})")
    p.add_argument("--skip-seed", action="store_true",
                   help="Skip trace seeding (project already has test data).")
    p.add_argument("--skip-pause", action="store_true",
                   help="Skip interactive pauses (run fully automated).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    env = get_env()
    project = args.project
    skip_pause = args.skip_pause

    # Dates used in filter scenarios
    now = datetime.now(tz=timezone.utc)
    cutoff_90  = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    cutoff_60  = (now - timedelta(days=60)).strftime("%Y-%m-%d")
    cutoff_30  = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    after_100  = (now - timedelta(days=100)).strftime("%Y-%m-%d")
    after_60   = (now - timedelta(days=60)).strftime("%Y-%m-%d")

    print("=" * 60)
    print("  Opik Trace Manager — End-to-End Test")
    print("=" * 60)
    print(f"  Workspace : {env['workspace']}")
    print(f"  Project   : {project}")
    print()

    # ------------------------------------------------------------------
    # Phase 1: Seed
    # ------------------------------------------------------------------
    if not args.skip_seed:
        section("Phase 1: Seeding test traces")
        print(f"  Creating {len(TRACE_SEEDS)} traces spread across different dates and tags:")
        tag_summary: dict[str, int] = {}
        for _, tags in TRACE_SEEDS:
            key = ", ".join(tags) if tags else "(untagged)"
            tag_summary[key] = tag_summary.get(key, 0) + 1
        for label, count in sorted(tag_summary.items()):
            print(f"    {label:<25} {count:>3} traces")
        print()
        seed_traces(env, project)

        # Brief wait for indexing
        print("  Waiting 3s for traces to be indexed...")
        time.sleep(3)
    else:
        section("Phase 1: Skipping seed (--skip-seed)")

    total = count_traces(env, project)
    print(f"  Project now has {total:,} total trace(s).")

    pause(
        f"Inspect '{project}' in the Opik UI to verify the seeded traces before continuing.",
        skip_pause,
    )

    # ------------------------------------------------------------------
    # Phase 2: List scenarios (read-only)
    # ------------------------------------------------------------------
    section("Phase 2: list — count-only inspection (no changes)")

    print("\n  2a. List ALL traces in the project (older-than-days 1 catches everything seeded)")
    run(["list", "--projects", project, "--older-than-days", "1"], "list all")

    print("\n  2b. List traces with tag 'sensitive'")
    run(["list", "--projects", project, "--tag", "sensitive"], "list by tag")

    print("\n  2c. List traces older than 90 days")
    run(["list", "--projects", project, "--before", cutoff_90], "list before 90d")

    print("\n  2d. List traces in a date window (between 100 and 60 days ago)")
    run(["list", "--projects", project, "--after", after_100, "--before", cutoff_60], "list window")

    print("\n  2e. List traces with 'internal' tag, excluding 'sensitive'")
    run(["list", "--projects", project, "--tag", "internal", "--exclude-tag", "sensitive"], "list tag+exclude")

    print("\n  2f. List traces by tag only — no date filter (all 'PII' traces regardless of age)")
    run(["list", "--projects", project, "--tag", "PII"], "list tag-only")

    tag_only_config_path = write_tag_only_config(project)
    print("\n  2g. List via tag-only config file (internal, excluding sensitive, no date)")
    print(f"      Config: {tag_only_config_path}")
    run(["list", "--config", tag_only_config_path], "list tag-only config")

    # ------------------------------------------------------------------
    # Phase 3: Delete dry-runs (no changes)
    # ------------------------------------------------------------------
    section("Phase 3: delete --dry-run (preview only, no changes)")

    print("\n  3a. Dry-run: delete traces tagged 'sensitive' older than 30 days")
    run(["delete", "--projects", project, "--tag", "sensitive", "--before", cutoff_30, "--dry-run"], "dry-run tag")

    print("\n  3b. Dry-run: delete traces older than 90 days")
    run(["delete", "--projects", project, "--before", cutoff_90, "--dry-run"], "dry-run before 90d")

    print("\n  3c. Dry-run: delete in date window")
    run(["delete", "--projects", project, "--after", after_100, "--before", cutoff_60, "--dry-run"], "dry-run window")

    print("\n  3d. Dry-run: delete ALL 'PII' traces — tag only, no date range")
    run(["delete", "--projects", project, "--tag", "PII", "--dry-run"], "dry-run tag-only")

    config_path = write_temp_config(project, TTL_RULES)
    print("\n  3e. Dry-run: apply TTL rules from config file")
    print(f"      Config: {config_path}")
    run(["delete", "--config", config_path, "--dry-run"], "dry-run ttl config")

    print("\n  3f. Dry-run: tag-only config (internal, excluding sensitive, no date)")
    print(f"      Config: {tag_only_config_path}")
    run(["delete", "--config", tag_only_config_path, "--dry-run"], "dry-run tag-only config")

    pause(
        "All dry-runs complete. Inspect the output above, then continue to execute real deletions.",
        skip_pause,
    )

    # ------------------------------------------------------------------
    # Phase 4: Real deletions
    # ------------------------------------------------------------------
    section("Phase 4: delete --yes (real deletions)")

    print("\n  4a. Delete ALL traces tagged 'PII' — tag only, no date filter")
    run(["delete", "--projects", project, "--tag", "PII", "--yes"], "delete PII tag-only")

    print(f"\n  Project trace count after 4a: {count_traces(env, project):,}")

    print("\n  4b. Delete traces tagged 'sensitive' older than 30 days")
    run(["delete", "--projects", project, "--tag", "sensitive", "--before", cutoff_30, "--yes"], "delete sensitive")

    print(f"\n  Project trace count after 4b: {count_traces(env, project):,}")

    print("\n  4c. Delete traces older than 90 days (no tag filter — catch-all)")
    run(["delete", "--projects", project, "--before", cutoff_90, "--yes"], "delete old untagged")

    print(f"\n  Project trace count after 4c: {count_traces(env, project):,}")

    pause(
        "Partial deletions done. Inspect the project in the UI to verify remaining traces.",
        skip_pause,
    )

    print("\n  4d. Delete via tag-only config (internal, excluding sensitive — all ages)")
    run(["delete", "--config", tag_only_config_path, "--yes"], "delete tag-only config")

    print(f"\n  Project trace count after 4d: {count_traces(env, project):,}")

    print("\n  4e. Delete remaining via TTL config (full pass)")
    run(["delete", "--config", config_path, "--yes"], "delete ttl config")

    final = count_traces(env, project)
    print(f"\n  Project trace count after 4e: {final:,}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("Test complete")
    print(f"  Project '{project}' has {final:,} trace(s) remaining.")
    if final > 0:
        print("  Some traces remain — these are within retention windows (e.g. recent 'sensitive' traces).")
    print()
    print("  Temp config files:", config_path, tag_only_config_path)
    print("  You can delete them with: rm", config_path, tag_only_config_path)
    print()


if __name__ == "__main__":
    main()
