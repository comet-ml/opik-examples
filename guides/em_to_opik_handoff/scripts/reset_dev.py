"""Remove development leftovers from Opik so the demo project only shows the real model.

Usage: uv run python scripts/reset_dev.py [--yes]

Deletes, in the demo's Opik project only:
- traces tagged detector:yolo11s-stock:dev-stock (runs made before a model was registered)
- experiments whose name ends in -dev-stock, or in -dev (subset and dev-dataset runs),
  with their traces
- the "<dataset>-dev" dataset
- with --queue only: the review queue, including any human annotations queued in it
  (re-create it with scripts/06_review_queue.py)
Nothing tagged with a registered model version is touched.
"""

from __future__ import annotations

import argparse

import opik
from opik.exceptions import ExperimentNotFound

from roadwork_demo.config import DEV_VERSION, VARIANTS, experiment_name, get_settings
from roadwork_demo.pipeline import current_handoff, dev_handoff
from roadwork_demo.review import find_review_queue


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="delete without the confirmation prompt")
    ap.add_argument("--queue", action="store_true", help="also delete the review queue")
    args = ap.parse_args()

    s = get_settings()
    client = opik.Opik()
    dev_tag = dev_handoff().model_tag()

    traces = client.search_traces(
        project_name=s.opik_project, filter_string=f'tags contains "{dev_tag}"', max_results=10000
    )
    experiments = []
    version = current_handoff().model_version
    names = {experiment_name(v, DEV_VERSION) for v in VARIANTS}
    names |= {experiment_name(v, ver, full_run=False) for v in VARIANTS for ver in (DEV_VERSION, version)}
    for name in sorted(names):
        try:
            # WHY: the lookup also returns experiments that only contain the name.
            experiments += [e for e in client.get_experiments_by_name(name) if e.name == name]
        except ExperimentNotFound:
            pass  # none left
    queue = find_review_queue(client, s) if args.queue else None
    queues = [queue] if queue else []
    dev_dataset = s.dev_dataset

    print(
        f"Project '{s.opik_project}': {len(traces)} dev traces, {len(experiments)} dev experiments, "
        f"{len(queues)} review queue(s) selected, dataset '{dev_dataset}'."
    )
    if not args.yes and input("Delete these? [y/N] ").strip().lower() != "y":
        print("Nothing deleted.")
        return

    # Traces of dev experiments carry the registered model's tag, so collect them by item.
    ids = {t.id for t in traces}
    ids |= {item.trace_id for e in experiments for item in e.get_items() if item.trace_id}
    ids = sorted(ids)
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
