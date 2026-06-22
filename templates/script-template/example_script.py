#!/usr/bin/env python3
"""One-line description of what this script does (replace me).

A runnable skeleton for an Opik utility script: loads credentials from the environment, falls
back to DRY_RUN when they are absent, and talks to Opik through the SDK client. Copy it with the
`scaffold-example` skill (`--template script-template --bucket scripts`), then fill the `TODO`.

Workflow:
  1. Dry-run   →  uv run example-script --dry-run
  2. Execute   →  set OPIK_API_KEY + OPIK_WORKSPACE, then  uv run example-script
"""

import argparse
import os
import sys

import opik

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_URL = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")

# DRY_RUN when credentials are absent, or forced with --dry-run.
DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=10, help="Sample option — replace with real flags.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen; touch nothing.")
    return parser


def run(client: opik.Opik | None, limit: int, dry_run: bool) -> None:
    # TODO: replace with the real work — fetch traces, manage datasets, call the REST client, etc.
    if dry_run:
        print(f"[DRY RUN] would process up to {limit} item(s) via Opik at {OPIK_URL}")
        return

    print(f"Processing up to {limit} item(s) via Opik at {OPIK_URL}...")
    # client is a live opik.Opik(); do the work here.


def main() -> int:
    args = build_parser().parse_args()
    dry_run = DRY_RUN or args.dry_run

    if dry_run:
        if not args.dry_run:
            print("OPIK_API_KEY / OPIK_WORKSPACE not set — running in DRY_RUN.", file=sys.stderr)
        run(None, args.limit, dry_run=True)
        return 0

    client = opik.Opik()
    run(client, args.limit, dry_run=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
