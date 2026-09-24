"""Curate highly rated recommendation traces into the golden evaluation dataset."""

import opik

from . import config

# Only report traces carry the replayable input/output contract offline evals need;
# capacity_audit traces store raw function args and would produce broken eval items.
REPORT_TRACE_NAMES = {"training_report"}


def curate(min_score: float, dataset_name: str, max_items: int) -> int:
    """Copy report traces whose judge/SME score >= min_score into the dataset.

    Returns the number of matching traces sent. Dataset inserts deduplicate identical
    items, so re-running after new ratings only adds the new traces.
    """
    client = opik.Opik(project_name=config.OPIK_PROJECT_NAME)
    traces = client.search_traces(
        project_name=config.OPIK_PROJECT_NAME,
        filter_string=f'feedback_scores."{config.JUDGE_SCORE_NAME}" >= {min_score}',
        max_results=max_items,
    )
    traces = [t for t in traces if t.name in REPORT_TRACE_NAMES]

    items = [
        {
            "input": t.input or {},
            "expected_output": t.output or {},
            # WHY: source="trace" is required for trace_id linkage; "sdk" items must not carry one.
            "source": "trace",
            "trace_id": str(t.id),
        }
        for t in traces
    ]
    if items:
        dataset = client.get_or_create_dataset(
            dataset_name, description="Capacity recommendations rated >= threshold; offline-eval reference"
        )
        dataset.insert(items)
    return len(items)
