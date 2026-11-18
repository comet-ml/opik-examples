from types import SimpleNamespace

import pytest

from roadwork_demo.gate import (
    GateRefusal,
    apply_decision,
    compare,
    decide,
    gate_notes,
    item_scores,
    latest,
    paired,
    require_current_in_production,
    same_dataset_version,
    sign_test_p,
)


class FakeModel:
    """Registry model that records status changes. `raises` fails every change; `deferred` accepts
    the request but leaves the status as it was, like an approval request from a non-owner."""

    def __init__(self, raises=None, deferred=False):
        self.calls = []
        self.raises = raises
        self.deferred = deferred
        self.statuses = {"1.0.0": "Production", "2.0.0": "Staging"}

    def set_status(self, version, status):
        self.calls.append((version, status))
        if self.raises:
            raise self.raises
        if not self.deferred:
            self.statuses[version] = status

    def status(self, version):
        return self.statuses[version]

    def find_versions(self, status=None):
        return sorted((v for v, s in self.statuses.items() if status in (None, s)), reverse=True)


CONFIG = {"verdict_model": "provider/model-a", "prompts": {"roadwork-verdict": "prompt text"}}


def fake_experiment(name, version_id, scores, metadata=CONFIG):
    """Experiment with one item per (dataset_item_id, verdict_accuracy value); None = not scored."""
    items = [
        SimpleNamespace(
            dataset_item_id=item_id,
            feedback_scores=[{"name": "judge_verdict_correct", "value": 1.0}]
            + ([] if value is None else [{"name": "verdict_accuracy", "value": value}]),
        )
        for item_id, value in scores.items()
    ]
    return SimpleNamespace(
        name=name,
        get_items=lambda: items,
        get_experiment_data=lambda: SimpleNamespace(dataset_version_id=version_id, metadata=metadata),
    )


def test_sign_test_known_values():
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(5, 5) == 1.0
    assert sign_test_p(10, 0) == pytest.approx(2 / 1024)
    assert sign_test_p(8, 2) == pytest.approx(0.109375)
    assert sign_test_p(2, 8) == sign_test_p(8, 2)


def test_paired_counts_wins_losses_and_delta():
    cand = {"a": 1.0, "b": 1.0, "c": 0.0, "d": 1.0}
    cur = {"a": 0.0, "b": 1.0, "c": 1.0, "d": 0.0}
    p = paired(cand, cur)
    assert (p.n, p.dropped, p.wins, p.losses) == (4, 0, 2, 1)
    assert p.delta == pytest.approx(0.25) and p.mean_candidate == 0.75 and p.mean_current == 0.5
    assert p.p_value == sign_test_p(2, 1)


def test_paired_uses_only_shared_items_and_reports_the_rest():
    p = paired({"a": 1.0, "b": 1.0}, {"a": 0.0, "z": 1.0})
    assert (p.n, p.dropped) == (1, 2)
    assert (p.mean_candidate, p.mean_current) == (1.0, 0.0)


def test_paired_with_no_shared_items_is_an_error():
    with pytest.raises(ValueError, match="no dataset items in common"):
        paired({"a": 1.0}, {"z": 1.0})


def test_decide():
    assert decide(0.05) == "promote"
    # WHY: the default min_delta is 0.03 and meeting it exactly is enough.
    assert decide(0.03) == "promote"
    assert decide(0.02) == "hold"
    # WHY: a tie never promotes, whatever min_delta says.
    assert decide(0.0, min_delta=0.0) == "hold"
    assert decide(-0.05) == "hold"


def test_apply_promote_swaps_statuses_candidate_first():
    model = FakeModel()
    lines = apply_decision(model, "2.0.0", "1.0.0", "promote")
    assert model.calls == [("2.0.0", "Production"), ("1.0.0", "Staging")] and len(lines) == 2
    assert model.statuses == {"1.0.0": "Staging", "2.0.0": "Production"}


def test_apply_hold_changes_nothing():
    model = FakeModel()
    assert apply_decision(model, "2.0.0", "1.0.0", "hold") == [] and model.calls == []


def test_apply_reports_a_refused_status_change_instead_of_raising():
    model = FakeModel(raises=RuntimeError("approval required"))
    lines = apply_decision(model, "2.0.0", "1.0.0", "promote")
    assert any("approval required" in line for line in lines)
    # WHY: demoting the current version after the promote failed would leave nothing in Production.
    assert model.calls == [("2.0.0", "Production")]


def test_apply_reports_a_deferred_status_change_and_keeps_the_current_version():
    model = FakeModel(deferred=True)
    lines = apply_decision(model, "2.0.0", "1.0.0", "promote")
    assert model.calls == [("2.0.0", "Production")]
    assert len(lines) == 1 and "Staging" in lines[0] and "2.0.0" in lines[0]


def test_apply_is_allowed_over_the_one_production_version():
    assert require_current_in_production(FakeModel(), "1.0.0") is None


def test_apply_is_refused_when_the_version_to_beat_is_not_in_production():
    model = FakeModel()
    model.statuses = {"1.0.0": "Production", "2.0.0": "Staging", "3.0.0": "Staging"}
    # WHY: promoting 3.0.0 over 2.0.0 would leave 1.0.0 in Production, never compared with 3.0.0.
    with pytest.raises(GateRefusal, match=r"2\.0\.0 is not the Production version.*1\.0\.0"):
        require_current_in_production(model, "2.0.0")


def test_apply_is_refused_when_several_versions_are_in_production():
    model = FakeModel()
    model.statuses = {"1.0.0": "Production", "2.0.0": "Production", "3.0.0": "Staging"}
    with pytest.raises(GateRefusal, match="2.0.0, 1.0.0"):
        require_current_in_production(model, "2.0.0")


def test_dataset_versions_must_match_and_be_known():
    assert same_dataset_version("v1", "v1") is True
    assert same_dataset_version("v1", "v2") is False
    assert same_dataset_version(None, "v1") is False
    assert same_dataset_version(None, None) is False


def test_item_scores_are_keyed_by_dataset_item_and_skip_unscored_items():
    experiment = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 1.0, "b": 0.0, "c": None})
    assert item_scores(experiment) == {"a": 1.0, "b": 0.0}


def test_compare_pairs_two_experiments_on_the_same_dataset_version():
    candidate = fake_experiment("detector_vlm-2.0.0", "v1", {"a": 1.0, "b": 1.0})
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0, "b": 1.0})
    p = compare(candidate, current)
    assert (p.n, p.wins, p.losses, p.delta) == (2, 1, 0, 0.5)


def test_compare_refuses_experiments_on_different_dataset_versions():
    candidate = fake_experiment("detector_vlm-2.0.0", "v2", {"a": 1.0})
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0})
    with pytest.raises(GateRefusal, match="dataset version"):
        compare(candidate, current)


def test_compare_refuses_experiments_run_with_different_verdict_models():
    candidate = fake_experiment(
        "detector_vlm-2.0.0", "v1", {"a": 1.0}, CONFIG | {"verdict_model": "provider/model-b"}
    )
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0})
    # WHY: otherwise a promote could reflect the model change, not the detector.
    with pytest.raises(GateRefusal, match="verdict_model.*model-b.*model-a"):
        compare(candidate, current)


def test_compare_refuses_experiments_run_with_different_prompts():
    candidate = fake_experiment(
        "detector_vlm-2.0.0", "v1", {"a": 1.0}, CONFIG | {"prompts": {"roadwork-verdict": "new"}}
    )
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0})
    with pytest.raises(GateRefusal, match="prompts"):
        compare(candidate, current)


def test_compare_accepts_experiments_without_a_recorded_configuration():
    candidate = fake_experiment("detector_vlm-2.0.0", "v1", {"a": 1.0}, None)
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0}, None)
    assert compare(candidate, current).delta == 1.0


def test_compare_refuses_experiments_that_share_no_items():
    candidate = fake_experiment("detector_vlm-2.0.0", "v1", {"a": 1.0})
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"z": 0.0})
    with pytest.raises(GateRefusal, match="no dataset items in common"):
        compare(candidate, current)


def test_compare_with_a_partial_candidate_uses_shared_items_and_counts_the_dropped():
    candidate = fake_experiment("detector_vlm-2.0.0", "v1", {"a": 1.0})
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0, "b": 1.0, "c": 1.0})
    p = compare(candidate, current)
    assert (p.n, p.dropped, p.mean_current) == (1, 2, 0.0)


def test_gate_notes_read_correctly_on_each_training_experiment():
    on_candidate, on_current = gate_notes("promote", "2.0.0", "1.0.0", 0.047)
    assert on_candidate == "promote vs 1.0.0, delta=+0.047"
    assert on_current == "candidate 2.0.0: promote, delta=+0.047"
    assert gate_notes("hold", "2.0.0", "1.0.0", -0.01)[0] == "hold vs 1.0.0, delta=-0.010"


def test_latest_picks_the_newest_of_same_named_experiments():
    # WHY: Opik ids are time-ordered (UUID v7), so the highest id is the most recent run.
    old = SimpleNamespace(id="01a1-0001", name="detector_vlm-1.0.0")
    new = SimpleNamespace(id="01a1-0002", name="detector_vlm-1.0.0")
    assert latest([new, old], "detector_vlm-1.0.0") is new
    assert latest([old], "detector_vlm-1.0.0") is old


def test_latest_ignores_experiments_that_only_share_a_prefix():
    # WHY: Opik's lookup by name also returns "detector_vlm-1.0.0-dev" for "detector_vlm-1.0.0".
    full = SimpleNamespace(id="01a1-0001", name="detector_vlm-1.0.0")
    dev = SimpleNamespace(id="01a1-0009", name="detector_vlm-1.0.0-dev")
    assert latest([dev, full], "detector_vlm-1.0.0") is full
    assert latest([dev], "detector_vlm-1.0.0") is None
