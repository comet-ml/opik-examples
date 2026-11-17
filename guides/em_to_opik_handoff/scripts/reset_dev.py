"""Remove development leftovers from Opik so the project only shows full runs.

Usage: uv run python scripts/reset_dev.py [--yes] [--queue]

Deletes, in this guide's Opik project only:
- experiments whose name ends in -dev (subset and dev-dataset runs), with their traces
- the "<dataset>-dev" dataset
- with --queue only: the review queue, including any human annotations queued in it
  (re-create it with scripts/06_review_queue.py)
Full runs are not touched, and neither is the detector_vlm-stock baseline.
"""

from __future__ import annotations

import argparse

import opik
from opik.exceptions import ExperimentNotFound

from roadwork_demo.config import get_settings, is_dev_experiment
from roadwork_demo.review import find_review_queue


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="delete without the confirmation prompt")
    ap.add_argument("--queue", action="store_true", help="also delete the review queue")
    args = ap.parse_args()

    s = get_settings()
    client = opik.Opik()
    try:
        # WHY: the lookup matches by substring, in this project only; keep exact dev names.
        experiments = [e for e in client.get_experiments_by_name("-dev") if is_dev_experiment(e.name)]
    except ExperimentNotFound:
        experiments = []
    queue = find_review_queue(client, s) if args.queue else None
    queues = [queue] if queue else []
    dev_dataset = s.dev_dataset

    print(
        f"Project '{s.project}': {len(experiments)} dev experiments "
        f"({', '.join(sorted(e.name for e in experiments)) or 'none'}), "
        f"{len(queues)} review queue(s) selected, dataset '{dev_dataset}'."
    )
    if not args.yes and input("Delete these? [y/N] ").strip().lower() != "y":
        print("Nothing deleted.")
        return

    # Traces of dev experiments carry the registered model's tag, so collect them by item.
    ids = sorted({item.trace_id for e in experiments for item in e.get_items() if item.trace_id})
    for q in queues:
        q.delete()
    if experiments:
        client.rest_client.experiments.delete_experiments_by_id(ids=[e.id for e in experiments])
    for i in range(0, len(ids), 500):
        client.rest_client.traces.delete_traces(ids=ids[i : i + 500])
    try:
        client.delete_dataset(dev_dataset)
    except Exception:
        pass  # already gone
    print("Dev leftovers deleted.")


if __name__ == "__main__":
    main()
