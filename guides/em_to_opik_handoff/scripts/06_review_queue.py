"""Send about 10 percent of detector+VLM traces to a human annotation queue.

Usage: uv run python scripts/06_review_queue.py [--detector production] [--fraction 0.10] [--minimum 12]
Safe to re-run: the feedback definition and queue are reused, traces are never added twice.
"""

from __future__ import annotations

import argparse
import random

import opik
from opik.config import OpikConfig
from opik.rest_api.types import CategoricalFeedbackDetailCreate, FeedbackCreate_Categorical
from opik.url_helpers import get_ui_url

from roadwork_demo.config import exit_if_dry_run, get_settings, variant_tag
from roadwork_demo.pipeline import handoff_or_exit
from roadwork_demo.review import find_review_queue, top_up
from roadwork_demo.verdicts import HUMAN_VERDICT as FEEDBACK_NAME
from roadwork_demo.verdicts import HUMAN_VERDICT_CATEGORIES as CATEGORIES

INSTRUCTIONS = (
    "Look at the camera frame and decide, for the vehicle's own direction of travel:\n"
    "- blocked: the road ahead is fully closed, no lane continues forward.\n"
    "- partial: a lane or part of a lane is closed, narrowed or shifted, traffic still passes.\n"
    "- clear: roadwork objects may be visible but all lanes ahead are open.\n"
    "Set human_verdict to your own answer, without looking at the model's verdict first."
)


def ensure_feedback_definition(client: opik.Opik) -> None:
    defs = client.rest_client.feedback_definitions
    existing = defs.find_feedback_definitions(name=FEEDBACK_NAME, size=50).content or []
    if any(d.name == FEEDBACK_NAME for d in existing):
        return
    defs.create_feedback_definition(
        request=FeedbackCreate_Categorical(
            name=FEEDBACK_NAME,
            description="Reviewer's own verdict for the frame.",
            details=CategoricalFeedbackDetailCreate(categories=CATEGORIES),
        )
    )
    print(f"Created feedback definition '{FEEDBACK_NAME}'")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detector", default=None, help="production, a registry version or stock")
    ap.add_argument("--fraction", type=float, default=0.10)
    ap.add_argument("--minimum", type=int, default=12)
    args = ap.parse_args()

    s = get_settings()
    exit_if_dry_run(s, f"sample detector_vlm traces into the review queue '{s.queue_name}'")
    handoff = handoff_or_exit(args.detector)
    client = opik.Opik()
    ensure_feedback_definition(client)

    queue = find_review_queue(client, s) or client.create_traces_annotation_queue(
        name=s.queue_name,
        project_name=s.project,
        description=f"10 percent human review of {handoff.model_tag()} verdicts.",
        instructions=INSTRUCTIONS,
        comments_enabled=True,
        feedback_definition_names=[FEEDBACK_NAME],
    )

    traces = client.search_traces(
        project_name=s.project,
        filter_string=f'tags contains "{variant_tag("detector_vlm")}"',
        max_results=5000,
    )
    traces = sorted((t for t in traces if handoff.model_tag() in (t.tags or [])), key=lambda t: t.id)
    if not traces:
        raise SystemExit(f"No detector_vlm traces tagged {handoff.model_tag()} yet.")

    k = min(len(traces), max(args.minimum, round(len(traces) * args.fraction)))
    chosen = random.Random(7).sample(traces, k)
    queued = {item.id for item in queue.get_items()}
    eligible = {t.id for t in traces}
    # WHY: only top up to the target. A fresh sample after new traces arrived would otherwise
    # add up to k more traces on every run.
    add_ids = set(top_up([t.id for t in chosen], queued, eligible, target=k))
    new = [t for t in chosen if t.id in add_ids]
    if new:
        queue.add_traces(new)
    print(
        f"Queue '{queue.name}': {len(traces)} eligible traces of {handoff.model_tag()}, sample of {k}, "
        f"{len(new)} added, {len(queued & eligible)} of them already queued."
    )
    print(f"Annotate at: {get_ui_url()}{OpikConfig().workspace}/annotation-queues/{queue.id}")


if __name__ == "__main__":
    main()
