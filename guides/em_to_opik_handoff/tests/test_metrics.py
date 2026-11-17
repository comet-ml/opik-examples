from roadwork_demo.metrics import VerdictAccuracy, judge_result_to_score


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
