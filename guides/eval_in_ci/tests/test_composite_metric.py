from typing import Any

from opik.evaluation.metrics import BaseMetric, score_result

from composite_metric import CompositePassMetric, failing_metrics_from_reason


class Const(BaseMetric):
    def __init__(self, name: str, value: float) -> None:
        super().__init__(name=name, track=False)
        self._value = value

    def score(self, *args: Any, **kwargs: Any) -> score_result.ScoreResult:
        return score_result.ScoreResult(name=self.name, value=self._value)


class Boom(BaseMetric):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, track=False)

    def score(self, *args: Any, **kwargs: Any) -> score_result.ScoreResult:
        raise RuntimeError("boom")


class Multi(BaseMetric):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, track=False)

    def score(self, *args: Any, **kwargs: Any) -> list[score_result.ScoreResult]:
        return [
            score_result.ScoreResult(name="m1", value=1.0),
            score_result.ScoreResult(name="m2", value=0.2),
        ]


def test_all_thresholds_met_yields_pass_and_zero_failed() -> None:
    m = CompositePassMetric([Const("a", 1.0), Const("b", 0.9)], {"a": 1.0, "b": 0.5})
    out = {r.name: r for r in m.score(expected={}, output={})}
    assert out["scenario_pass"].value == 1.0
    assert out["scenario_pass"].reason == "all thresholds met"
    assert out["n_metrics_failed"].value == 0.0
    assert out["a"].value == 1.0 and out["b"].value == 0.9


def test_one_below_threshold_fails_with_named_reason() -> None:
    m = CompositePassMetric([Const("a", 0.35), Const("b", 1.0)], {"a": 0.9, "b": 1.0})
    out = {r.name: r for r in m.score()}
    assert out["scenario_pass"].value == 0.0
    assert out["scenario_pass"].reason == "failed: a 0.35 < 0.90"
    assert out["n_metrics_failed"].value == 1.0


def test_raising_submetric_counts_as_unscored_failure() -> None:
    m = CompositePassMetric([Boom("a"), Const("b", 1.0)], {"a": 1.0, "b": 1.0})
    out = {r.name: r for r in m.score()}
    assert out["a"].scoring_failed is True
    assert out["scenario_pass"].reason == "failed: a unscored"


def test_threshold_for_missing_metric_fails() -> None:
    m = CompositePassMetric([Const("a", 1.0)], {"a": 1.0, "zzz": 1.0})
    out = {r.name: r for r in m.score()}
    assert out["scenario_pass"].reason == "failed: zzz missing"


def test_list_returning_submetric_is_flattened_and_gated() -> None:
    m = CompositePassMetric([Multi("multi")], {"m2": 0.5})
    results = m.score()
    assert [r.name for r in results] == [
        "m1",
        "m2",
        "scenario_pass",
        "n_metrics_failed",
    ]
    assert results[2].reason == "failed: m2 0.20 < 0.50"


def test_unthresholded_metric_is_ignored() -> None:
    m = CompositePassMetric([Const("a", 0.0), Const("b", 1.0)], {"b": 1.0})
    out = {r.name: r for r in m.score()}
    assert out["scenario_pass"].value == 1.0
    assert out["a"].value == 0.0


def test_failing_metrics_from_reason_roundtrip() -> None:
    assert failing_metrics_from_reason("failed: a 0.35 < 0.90; sim valid unscored") == (
        "a",
        "sim valid",
    )
    assert failing_metrics_from_reason("all thresholds met") == ()
    assert failing_metrics_from_reason(None) == ()


def test_names_with_spaces_roundtrip_through_composite() -> None:
    m = CompositePassMetric(
        [Const("tool use", 0.1), Boom("sim valid"), Const("x", 1.0)],
        {"tool use": 0.9, "sim valid": 1.0, "x": 1.0, "gone away": 1.0},
    )
    reason = {r.name: r for r in m.score()}["scenario_pass"].reason
    assert failing_metrics_from_reason(reason) == ("tool use", "sim valid", "gone away")


def test_nan_submetric_value_is_unscored_failure() -> None:
    m = CompositePassMetric([Const("a", float("nan"))], {"a": 0.5})
    out = {r.name: r for r in m.score()}
    assert out["scenario_pass"].value == 0.0
    assert out["scenario_pass"].reason == "failed: a unscored"
    assert out["n_metrics_failed"].value == 1.0
