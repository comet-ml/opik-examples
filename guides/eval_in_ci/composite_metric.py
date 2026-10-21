"""Composite pass/fail metric for eval-in-CI.

Wraps several Opik metrics, passes their scores through unchanged, and adds
two extra scores: a binary pass/fail for the whole scenario and a count of
failed metrics. Only metrics named in ``thresholds`` gate the result.
"""

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from opik.evaluation.metrics import BaseMetric, score_result

N_METRICS_FAILED = "n_metrics_failed"
DEFAULT_PASS_NAME = "scenario_pass"

_ALL_MET_REASON = "all thresholds met"
_FAILED_PREFIX = "failed: "
_BELOW_RE = re.compile(r"^(?P<name>.+) -?\d+(?:\.\d+)? < -?\d+(?:\.\d+)?$")
_KEYWORD_RE = re.compile(r"^(?P<name>.+) (?:unscored|missing)$")


class CompositePassMetric(BaseMetric):
    """Run sub-metrics and gate a scenario on per-metric thresholds."""

    def __init__(
        self,
        metrics: Sequence[BaseMetric],
        thresholds: Mapping[str, float],
        name: str = DEFAULT_PASS_NAME,
        track: bool = True,
    ) -> None:
        super().__init__(name=name, track=track)
        self._metrics = list(metrics)
        self._thresholds = dict(thresholds)

    def _run_metric(
        self, metric: BaseMetric, kwargs: dict[str, Any]
    ) -> list[score_result.ScoreResult]:
        try:
            result = metric.score(**kwargs)
        except Exception as exc:
            return [
                score_result.ScoreResult(
                    name=metric.name,
                    value=0.0,
                    reason=str(exc),
                    scoring_failed=True,
                )
            ]
        if isinstance(result, list):
            return list(result)
        return [result]

    def score(self, **kwargs: Any) -> list[score_result.ScoreResult]:
        results: list[score_result.ScoreResult] = []
        for metric in self._metrics:
            results.extend(self._run_metric(metric, kwargs))

        by_name = {r.name: r for r in results}
        failures: list[str] = []
        for metric_name, threshold in self._thresholds.items():
            found = by_name.get(metric_name)
            if found is None:
                failures.append(f"{metric_name} missing")
            elif found.scoring_failed or math.isnan(found.value):
                failures.append(f"{metric_name} unscored")
            elif found.value < threshold:
                failures.append(f"{metric_name} {found.value:.2f} < {threshold:.2f}")

        reason = (
            _ALL_MET_REASON if not failures else _FAILED_PREFIX + "; ".join(failures)
        )
        results.append(
            score_result.ScoreResult(
                name=self.name,
                value=0.0 if failures else 1.0,
                reason=reason,
            )
        )
        results.append(
            score_result.ScoreResult(name=N_METRICS_FAILED, value=float(len(failures)))
        )
        return results


def failing_metrics_from_reason(reason: str | None) -> tuple[str, ...]:
    """Parse a composite reason back into the names of the failed metrics."""
    if not reason or not reason.startswith(_FAILED_PREFIX):
        return ()
    names: list[str] = []
    for part in reason[len(_FAILED_PREFIX) :].split("; "):
        match = _BELOW_RE.match(part) or _KEYWORD_RE.match(part)
        if match:
            names.append(match.group("name"))
    return tuple(names)
