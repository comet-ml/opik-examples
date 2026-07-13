"""A sample user-defined metric for Opik online evaluation (Python-metric rules).

The whole source of this file is embedded into the rule's `code.metric`. Opik runs it
server-side, instantiates the metric, and calls `score(**arguments)`. The keys in the rule's
`arguments` map must match the parameter names of `score` below (`output`, `reference`).
"""

from typing import Any

from opik.evaluation.metrics import base_metric, score_result


class EqualsMetric(base_metric.BaseMetric):
    """Scores 1.0 when the output exactly equals the reference, else 0.0."""

    def __init__(self, name: str = "equals_metric"):
        super().__init__(name=name, track=False)

    def score(self, output: str, reference: str, **ignored: Any) -> score_result.ScoreResult:
        value = 1.0 if output == reference else 0.0
        return score_result.ScoreResult(value=value, name=self.name)
