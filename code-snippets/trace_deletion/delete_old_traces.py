#!/usr/bin/env python3
"""
Delete Opik traces older than N months for specific projects.

Usage:
    source ../../.env.dev && python delete_old_traces.py
    source ../../.env.dev && python delete_old_traces.py --dry-run
    source ../../.env.dev && python delete_old_traces.py --projects "my-project" "another-project" --months 3

Requires environment variables:
    OPIK_API_KEY       - Opik API key
    OPIK_WORKSPACE     - Workspace name
    OPIK_BASE_URL      - Base URL (default: https://www.comet.com)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://www.comet.com"
BATCH_SIZE = 1000          # Max allowed by API
RATE_LIMIT_DELAY = 0.2     # Seconds between batch delete requests


def get_config() -> dict:
    api_key = os.environ.get("OPIK_API_KEY")
    workspace = os.environ.get("OPIK_WORKSPACE")
    base_url = os.environ.get("OPIK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    if not api_key:
        print("ERROR: OPIK_API_KEY environment variable is not set.")
        sys.exit(1)
    if not workspace:
        print("ERROR: OPIK_WORKSPACE environment variable is not set.")
        sys.exit(1)

    return {
        "api_key": api_key,
        "workspace": workspace,
        "base_url": base_url,
    }


def make_headers(config: dict) -> dict:
    return {
        "Authorization": f"Bearer {config['api_key']}",
        "Comet-Workspace": config["workspace"],
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Project lookup
# ---------------------------------------------------------------------------

def get_project_id(config: dict, project_name: str) -> Optional[str]:
    """Resolve a project name to its UUID."""
    url = f"{config['base_url']}/opik/api/v1/private/projects"
    params = {"name": project_name, "workspace_name": config["workspace"]}
    resp = requests.get(url, headers=make_headers(config), params=params)
    resp.raise_for_status()

    data = resp.json()
    projects = data.get("content", [])
    for p in projects:
        if p.get("name") == project_name:
            return p["id"]

    return None


# ---------------------------------------------------------------------------
# Trace listing
# ---------------------------------------------------------------------------

def list_traces_before(
    config: dict,
    project_name: str,
    cutoff: datetime,
    page: int = 1,
    page_size: int = BATCH_SIZE,
) -> dict:
    """Return one page of traces created before `cutoff`."""
    url = f"{config['base_url']}/opik/api/v1/private/traces"
    params = {
        "project_name": project_name,
        "to_time": cutoff.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",  # millisecond precision
        "page": page,
        "size": page_size,
    }
    resp = requests.get(url, headers=make_headers(config), params=params)
    resp.raise_for_status()
    return resp.json()


def collect_trace_ids(
    config: dict,
    project_name: str,
    cutoff: datetime,
) -> tuple[list[str], str]:
    """Fetch all trace IDs older than `cutoff`. Returns (ids, project_id)."""
    all_ids: list[str] = []
    project_id: Optional[str] = None
    page = 1

    print(f"  Listing traces before {cutoff.date()} ...", flush=True)

    while True:
        data = list_traces_before(config, project_name, cutoff, page=page)
        content = data.get("content", [])
        total = data.get("total", 0)

        if not content:
            break

        for trace in content:
            all_ids.append(trace["id"])
            if project_id is None:
                project_id = trace.get("project_id")

        print(f"    Page {page}: {len(content)} traces (total so far: {len(all_ids)} / {total})")

        # Stop if we've fetched everything
        if len(all_ids) >= total:
            break

        page += 1

    # Fallback: look up project_id by name if traces didn't include it
    if project_id is None and all_ids:
        project_id = get_project_id(config, project_name)

    return all_ids, project_id


# ---------------------------------------------------------------------------
# Batch deletion
# ---------------------------------------------------------------------------

def batch_delete_traces(
    config: dict,
    trace_ids: list[str],
    project_id: Optional[str],
    dry_run: bool,
) -> int:
    """Delete traces in batches of BATCH_SIZE. Returns count deleted."""
    total_deleted = 0

    for i in range(0, len(trace_ids), BATCH_SIZE):
        batch = trace_ids[i : i + BATCH_SIZE]

        if dry_run:
            print(f"    [DRY RUN] Would delete {len(batch)} traces (batch {i // BATCH_SIZE + 1})")
            total_deleted += len(batch)
            continue

        url = f"{config['base_url']}/opik/api/v1/private/traces/delete"
        payload: dict = {"ids": batch}
        if project_id:
            payload["project_id"] = project_id

        resp = requests.post(url, headers=make_headers(config), json=payload)
        resp.raise_for_status()

        total_deleted += len(batch)
        print(f"    Deleted batch {i // BATCH_SIZE + 1}: {len(batch)} traces (total: {total_deleted})")

        if i + BATCH_SIZE < len(trace_ids):
            time.sleep(RATE_LIMIT_DELAY)

    return total_deleted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete Opik traces older than N months for specific projects."
    )
    parser.add_argument(
        "--projects",
        nargs="+",
        metavar="PROJECT_NAME",
        help="Project names to clean up. Defaults to PROJECT_NAMES list in the script.",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="Delete traces older than this many months (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be deleted without actually deleting anything.",
    )
    return parser.parse_args()


# ============================================================
# CONFIGURE: list of project names to clean up
# ============================================================
PROJECT_NAMES = [
    # "my-production-project",
    # "another-project",
]
# ============================================================


def main():
    args = parse_args()
    config = get_config()

    project_names = args.projects or PROJECT_NAMES
    if not project_names:
        print(
            "ERROR: No projects specified. Pass --projects <name> or set PROJECT_NAMES in the script."
        )
        sys.exit(1)

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=args.months * 30)
    mode = "[DRY RUN] " if args.dry_run else ""

    print(f"{mode}Deleting Opik traces older than {args.months} months")
    print(f"  Workspace : {config['workspace']}")
    print(f"  Base URL  : {config['base_url']}")
    print(f"  Cutoff    : {cutoff.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Projects  : {project_names}")
    print()

    grand_total = 0

    for project_name in project_names:
        print(f"Project: {project_name}")

        try:
            trace_ids, project_id = collect_trace_ids(config, project_name, cutoff)
        except requests.HTTPError as e:
            print(f"  ERROR listing traces: {e}")
            if e.response is not None:
                print(f"  Response: {e.response.text}")
            continue

        if not trace_ids:
            print("  No traces found before cutoff date.")
            print()
            continue

        print(f"  Found {len(trace_ids)} traces to delete")

        try:
            deleted = batch_delete_traces(config, trace_ids, project_id, dry_run=args.dry_run)
            grand_total += deleted
            print(f"  Done: {deleted} traces {'would be ' if args.dry_run else ''}deleted")
        except requests.HTTPError as e:
            print(f"  ERROR during deletion: {e}")
            if e.response is not None:
                print(f"  Response: {e.response.text}")

        print()

    summary_verb = "would be deleted" if args.dry_run else "deleted"
    print(f"Complete. Grand total: {grand_total} traces {summary_verb} across {len(project_names)} project(s).")


if __name__ == "__main__":
    main()
