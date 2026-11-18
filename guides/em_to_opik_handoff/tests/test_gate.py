from types import SimpleNamespace

import pytest

from roadwork_demo.gate import (
    GateRefusal,
    apply_decision,
    compare,
    decide,
    find_experiment,
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
        get_items=lambda truncate=False: items if truncate else pytest.fail("items fetched untruncated"),
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


def test_decide_promotes_at_the_threshold_despite_float_rounding():
    # WHY: 59 against 56 correct of 100 is a gain of 3 points, but 0.59 - 0.56 < 0.03 in floats.
    assert 59 / 100 - 56 / 100 < 0.03
    assert decide(59 / 100 - 56 / 100) == "promote"
    assert decide(56 / 100 - 53 / 100) == "promote"
    assert decide(0.029) == "hold"


def test_apply_promote_swaps_statuses_candidate_first():
    model = FakeModel()
    applied = apply_decision(model, "2.0.0", "1.0.0", "promote")
    assert model.calls == [("2.0.0", "Production"), ("1.0.0", "Staging")]
    assert applied.done is True and len(applied.lines) == 2
    assert model.statuses == {"1.0.0": "Staging", "2.0.0": "Production"}


def test_apply_hold_changes_nothing():
    model = FakeModel()
    applied = apply_decision(model, "2.0.0", "1.0.0", "hold")
    assert applied.done is True and applied.lines == [] and model.calls == []


def test_apply_reports_a_refused_status_change_instead_of_raising():
    model = FakeModel(raises=RuntimeError("approval required"))
    applied = apply_decision(model, "2.0.0", "1.0.0", "promote")
    assert applied.done is False and any("approval required" in line for line in applied.lines)
    # WHY: demoting the current version after the promote failed would leave nothing in Production.
    assert model.calls == [("2.0.0", "Production")]


def test_apply_reports_a_deferred_status_change_and_keeps_the_current_version():
    model = FakeModel(deferred=True)
    applied = apply_decision(model, "2.0.0", "1.0.0", "promote")
    assert model.calls == [("2.0.0", "Production")]
    assert applied.done is False
    assert len(applied.lines) == 1 and "Staging" in applied.lines[0] and "2.0.0" in applied.lines[0]


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


def test_compare_refuses_an_experiment_that_scored_only_part_of_the_items():
    # WHY: an aborted run that is the newest of its name must not promote on a handful of items.
    candidate = fake_experiment("detector_vlm-2.0.0", "v1", {"a": 1.0})
    current = fake_experiment("detector_vlm-1.0.0", "v1", {"a": 0.0, "b": 1.0, "c": 1.0})
    with pytest.raises(GateRefusal, match="only 1 of 3 dataset items"):
        compare(candidate, current)


def test_compare_tolerates_a_few_items_that_one_side_could_not_score():
    ids = [f"item-{i}" for i in range(20)]
    candidate = fake_experiment("detector_vlm-2.0.0", "v1", dict.fromkeys(ids, 1.0))
    current = fake_experiment("detector_vlm-1.0.0", "v1", dict.fromkeys(ids[:18], 0.0))
    p = compare(candidate, current)
    assert (p.n, p.dropped) == (18, 2)


def test_gate_notes_read_correctly_on_each_training_experiment():
    on_candidate, on_current = gate_notes("promote", "2.0.0", "1.0.0", 0.047)
    assert on_candidate == "promote vs 1.0.0, delta=+0.047"
    assert on_current == "candidate 2.0.0: promote, delta=+0.047"
    assert gate_notes("hold", "2.0.0", "1.0.0", -0.01)[0] == "hold vs 1.0.0, delta=-0.010"


def test_gate_notes_say_when_a_promote_did_not_reach_the_registry():
    on_candidate, on_current = gate_notes("promote", "2.0.0", "1.0.0", 0.047, applied=False)
    assert on_candidate == "promote (not applied) vs 1.0.0, delta=+0.047"
    assert on_current == "candidate 2.0.0: promote (not applied), delta=+0.047"


def test_find_experiment_returns_the_newest_exact_match_or_none():
    from opik.exceptions import ExperimentNotFound

    old = SimpleNamespace(id="01a1-0001", name="vlm_only")
    new = SimpleNamespace(id="01a1-0002", name="vlm_only")
    found = SimpleNamespace(get_experiments_by_name=lambda name: [old, new])
    assert find_experiment(found, "vlm_only") is new

    def not_found(name):
        raise ExperimentNotFound(name)

    assert find_experiment(SimpleNamespace(get_experiments_by_name=not_found), "vlm_only") is None


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
