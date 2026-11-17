"""Lookup of the human review (annotation) queue in Opik."""

from __future__ import annotations

from roadwork_demo.config import Settings


def find_review_queue(client, s: Settings):
    """The demo's traces annotation queue, or None if it was not created yet."""
    queues = client.get_traces_annotation_queues(project_name=s.project)
    return next((q for q in queues if q.name == s.queue_name), None)


def top_up(sampled_ids: list[str], already: set[str], target: int) -> list[str]:
    """Ids to add so the queue reaches `target` items, in sample order, never re-adding."""
    missing = max(0, target - len(already))
    return [i for i in sampled_ids if i not in already][:missing]
