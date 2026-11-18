from types import SimpleNamespace

from roadwork_demo.metrics import VerdictAccuracy, judge_result_to_score, per_class_accuracy


def test_accuracy_match():
    r = VerdictAccuracy().score(verdict="blocked", expected_verdict="blocked")
    assert r.value == 1.0 and r.name == "verdict_accuracy"


def test_accuracy_mismatch():
    assert VerdictAccuracy().score(verdict="partial", expected_verdict="blocked").value == 0.0


def test_accuracy_invalid():
    r = VerdictAccuracy().score(verdict="invalid", expected_verdict="clear")
    assert r.value == 0.0 and "invalid" in r.reason


def test_accuracy_ignores_extra_dataset_fields():
    # Opik passes the dataset item fields and the task output fields as keyword arguments.
    r = VerdictAccuracy().score(
        verdict="clear", expected_verdict="clear", image="x", file_name="y", reason="r", detections=[]
    )
    assert r.value == 1.0


def test_judge_helper():
    assert judge_result_to_score({"correct": True, "reason": "ok"}) == (1.0, "ok")
    assert judge_result_to_score({"correct": False, "reason": "no barrier"}) == (0.0, "no barrier")


def test_judge_helper_without_decision_scores_zero():
    value, reason = judge_result_to_score(None)
    assert value == 0.0 and reason
    assert judge_result_to_score({"reason": "x"})[0] == 0.0


def _result(expected, value, name="verdict_accuracy", scoring_failed=False):
    """Shaped like opik.evaluation.test_result.TestResult, as far as per_class_accuracy reads it."""
    return SimpleNamespace(
        test_case=SimpleNamespace(dataset_item_content={"expected_verdict": expected}),
        score_results=[
            SimpleNamespace(name=name, value=value, scoring_failed=scoring_failed),
            SimpleNamespace(name="judge_verdict_correct", value=1.0, scoring_failed=False),
        ],
    )


def test_per_class_accuracy_scores():
    results = [_result("blocked", 1.0), _result("blocked", 0.0), _result("clear", 1.0)]
    scores = {s.name: s.value for s in per_class_accuracy(results)}
    assert scores == {"accuracy_blocked": 0.5, "accuracy_clear": 1.0}


def test_per_class_accuracy_skips_failed_scores():
    assert per_class_accuracy([_result("blocked", 0.0, scoring_failed=True)]) == []
