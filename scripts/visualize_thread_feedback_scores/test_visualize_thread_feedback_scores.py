from __future__ import annotations

from types import SimpleNamespace

from visualize_thread_feedback_scores import (
    sample_turn_scores,
    traces_to_turn_scores,
)


def test_sample_turn_scores_has_multiple_metrics() -> None:
    turns = sample_turn_scores()
    assert len(turns) >= 3
    assert "helpfulness" in turns[0].scores


def test_traces_to_turn_scores_orders_by_start_time() -> None:
    traces = [
        SimpleNamespace(
            id="later",
            start_time="2026-01-01T12:00:00+00:00",
            feedback_scores=[SimpleNamespace(name="quality", value=0.2)],
        ),
        SimpleNamespace(
            id="earlier",
            start_time="2026-01-01T11:00:00+00:00",
            feedback_scores=[SimpleNamespace(name="quality", value=0.9)],
        ),
    ]
    turns = traces_to_turn_scores(traces)
    assert [t.trace_id for t in turns] == ["earlier", "later"]
    assert turns[0].scores["quality"] == 0.9
    assert turns[1].turn == 2
