"""Lookup of the human review (annotation) queue in Opik."""

from __future__ import annotations

from roadwork_demo.config import Settings


def find_review_queue(client, s: Settings):
    """The demo's traces annotation queue, or None if it was not created yet."""
    queues = client.get_traces_annotation_queues(project_name=s.project)
    return next((q for q in queues if q.name == s.queue_name), None)


def top_up(sampled_ids: list[str], queued: set[str], eligible: set[str], target: int) -> list[str]:
    """Ids to add so the queue holds `target` of the `eligible` traces, never re-adding one."""
    # WHY eligible: the queue also holds traces of earlier detector versions. Counting those
    # would leave no room for the version that is in Production now.
    missing = max(0, target - len(queued & eligible))
    return [i for i in sampled_ids if i not in queued][:missing]
