import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import eval_compare as ec

PASS = "scenario_pass"


def _score(name: str, value: float, reason: str | None = None) -> dict[str, Any]:
    return {"name": name, "value": value, "reason": reason}


def _ok() -> list[dict[str, Any]]:
    return [_score(PASS, 1.0, "all thresholds met")]


def _bad(metric: str = "a") -> list[dict[str, Any]]:
    return [_score(PASS, 0.0, f"failed: {metric} 0.35 < 0.90")]


def row(
    item_id: str,
    label: str | None,
    runs: dict[str, list[list[dict[str, Any]]]],
) -> SimpleNamespace:
    """runs maps experiment id -> list of runs, each run a list of score dicts."""
    items = []
    for exp_id, exp_runs in runs.items():
        for i, scores in enumerate(exp_runs):
            items.append(
                SimpleNamespace(
                    experiment_id=exp_id,
                    dataset_item_id=item_id,
                    trace_id=f"t-{item_id}-{exp_id}-{i}",
                    feedback_scores=[SimpleNamespace(**s) for s in scores],
                )
            )
    return SimpleNamespace(id=item_id, data={"scenario_id": label}, experiment_items=items)


def _classify(rows: list[SimpleNamespace], **kwargs: Any) -> ec.Comparison:
    kwargs.setdefault("baseline_id", "B")
    return ec.classify(ec.rows_to_item_runs(rows), candidate_id="C", **kwargs)


def _meta(**kwargs: Any) -> ec.DigestMeta:
    defaults: dict[str, Any] = dict(
        baseline_name="base",
        candidate_name="cand",
        compare_url="http://x/compare",
        trace_url=lambda _tid: None,
        policy_source="defaults",
        server_version="1.0",
        git={"sha": "abc"},
    )
    defaults.update(kwargs)
    return ec.DigestMeta(**defaults)


def _four_items() -> list[SimpleNamespace]:
    return [
        row("i1", "s1", {"B": [_ok()], "C": [_bad("a")]}),
        row("i2", "s2", {"B": [_bad()], "C": [_ok()]}),
        row("i3", "s3", {"B": [_bad()], "C": [_bad("b")]}),
        row("i4", "s4", {"B": [_ok()], "C": [_ok()]}),
    ]


def test_rows_to_item_runs_reads_scores_and_label() -> None:
    r = row("i1", "s1", {"B": [[_score(PASS, 1.0, "ok"), _score("m", 0.5)]]})
    r.experiment_items.append(
        SimpleNamespace(experiment_id="B", dataset_item_id="i1", trace_id=None, feedback_scores=None)
    )
    runs = ec.rows_to_item_runs([r])
    assert len(runs) == 2
    assert runs[0].label == "s1"
    assert runs[0].dataset_item_id == "i1"
    assert runs[0].experiment_id == "B"
    assert runs[0].trace_id == "t-i1-B-0"
    assert runs[0].scores == (
        ec.RunScore(PASS, 1.0, "ok"),
        ec.RunScore("m", 0.5, None),
    )
    assert runs[1].scores == ()
    assert runs[1].trace_id is None


def test_classify_flags_newly_failing_passing_still_failing() -> None:
    cmp = _classify(_four_items())
    assert [o.dataset_item_id for o in cmp.newly_failing] == ["i1"]
    assert [o.dataset_item_id for o in cmp.newly_passing] == ["i2"]
    assert [o.dataset_item_id for o in cmp.still_failing] == ["i3"]
    assert cmp.newly_failing[0].failing_metrics == ("a",)
    assert cmp.still_failing[0].failing_metrics == ("b",)
    assert cmp.newly_failing[0].worst_trace_id == "t-i1-C-0"
    assert cmp.items_scored == 4
    assert cmp.pass_rate_baseline == 0.5
    assert cmp.pass_rate_candidate == 0.5
    assert cmp.pass_rule == "all 1 trials"
    assert cmp.metric_means[PASS] == (0.5, 0.5)


def test_item_only_in_candidate_is_new_not_regression() -> None:
    rows = [
        row("i1", "s1", {"B": [_ok()], "C": [_ok()]}),
        row("i9", "s9", {"C": [_bad()]}),
    ]
    cmp = _classify(rows)
    assert [o.dataset_item_id for o in cmp.new_items] == ["i9"]
    assert cmp.newly_failing == []
    assert cmp.still_failing == []
    assert cmp.new_items[0].baseline_passed is None


def test_missing_pass_score_counts_as_failed_unscored() -> None:
    rows = [row("i1", "s1", {"B": [_ok()], "C": [[_score("m", 0.9)]]})]
    cmp = _classify(rows)
    assert len(cmp.newly_failing) == 1
    assert cmp.newly_failing[0].failing_metrics == ("unscored",)


def test_trials_default_rule_requires_all_runs() -> None:
    rows = [row("i1", "s1", {"B": [_ok()] * 3, "C": [_ok(), _ok(), _bad()]})]
    cmp = _classify(rows)
    assert cmp.pass_rule == "all 3 trials"
    assert [o.dataset_item_id for o in cmp.flaky] == ["i1"]
    assert cmp.flaky[0].candidate_passed is False
    assert cmp.flaky[0].candidate_pass_runs == 2
    assert cmp.flaky[0].candidate_runs == 3
    assert cmp.newly_failing == []
    assert cmp.pass_rate_candidate == 0.0


def test_pass_threshold_override_changes_rule_string() -> None:
    rows = [row("i1", "s1", {"B": [_ok()] * 3, "C": [_ok(), _ok(), _bad()]})]
    cmp = _classify(rows, pass_threshold=2)
    assert cmp.pass_rule == "2 of 3 trials (differs from UI)"
    assert cmp.flaky[0].candidate_passed is True
    assert cmp.pass_rate_candidate == 1.0


def test_flaky_excluded_from_regressions_by_default() -> None:
    rows = [
        row("i1", "s1", {"B": [_ok()] * 3, "C": [_ok(), _bad(), _bad()]}),
    ]
    cmp = _classify(rows)
    policy = ec.Policy(min_items=1, pass_rate=0.0)
    assert cmp.newly_failing == []
    assert ec.evaluate_policy(cmp, policy).status == "ok"
    counted = ec.evaluate_policy(cmp, ec.Policy(min_items=1, pass_rate=0.0, flaky_policy="count"))
    assert counted.status == "hold"
    assert any(c.name == "max_regressions" and not c.passed for c in counted.criteria)


def test_no_baseline_without_mark_gives_no_baseline() -> None:
    cmp = _classify([row("i1", "s1", {"C": [_ok()]})], baseline_id=None)
    verdict = ec.evaluate_policy(cmp, ec.Policy())
    assert verdict.status == "no_baseline"
    assert verdict.passed is True
    md = ec.render_markdown(cmp, verdict, _meta(baseline_name=None))
    assert "Baseline: none found - merge to main with --mark-baseline to create one" in md


def test_no_baseline_gives_baseline_created() -> None:
    rows = [
        row("i1", "s1", {"C": [_ok()]}),
        row("i2", "s2", {"C": [_bad()]}),
    ]
    cmp = _classify(rows, baseline_id=None)
    assert cmp.pass_rate_baseline is None
    assert cmp.new_items == []
    assert cmp.newly_failing == []
    assert [o.dataset_item_id for o in cmp.still_failing] == ["i2"]
    verdict = ec.evaluate_policy(cmp, ec.Policy(), mark_baseline=True)
    assert verdict.status == "baseline_created"
    assert verdict.passed is True
    assert [c.name for c in verdict.criteria] == [
        "min_items",
        "max_regressions",
        "pass_rate",
        "flaky_policy",
    ]
    md = ec.render_markdown(cmp, verdict, _meta(baseline_name=None, mark_baseline=True))
    assert "Pass rate: n/a -> 0.50" in md
    assert "Baseline: this run (cand)" in md


def test_digest_names_the_baseline() -> None:
    cmp = _classify([row("i1", "s1", {"B": [_ok()], "C": [_ok()]})])
    md = ec.render_markdown(cmp, ec.evaluate_policy(cmp, ec.Policy()), _meta())
    lines = md.splitlines()
    assert lines[2] == ""
    assert lines[3] == "Baseline: base (B)"


def test_policy_hold_beats_insufficient_evidence() -> None:
    rows = [
        row("i1", "s1", {"B": [_ok()], "C": [_bad()]}),
        row("i2", "s2", {"B": [_ok()], "C": [_ok()]}),
        row("i3", "s3", {"B": [_ok()], "C": [_ok()]}),
    ]
    cmp = _classify(rows)
    verdict = ec.evaluate_policy(cmp, ec.Policy())
    assert verdict.status == "hold"
    assert verdict.passed is False
    by_name = {c.name: c for c in verdict.criteria}
    assert by_name["min_items"].passed is False
    assert by_name["max_regressions"].passed is False
    assert by_name["max_regressions"].observed == "1"

    healthy = _classify([row("i1", "s1", {"B": [_ok()], "C": [_ok()]})])
    assert ec.evaluate_policy(healthy, ec.Policy()).status == "insufficient_evidence"
    assert ec.evaluate_policy(healthy, ec.Policy(min_items=1)).status == "ok"


def test_load_policy_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "policy.yaml"
    p.write_text("min_items: 3\nbogus_key: 1\n")
    with pytest.raises(ec.PolicyError, match="unknown policy key: bogus_key"):
        ec.load_policy(p)

    ok = tmp_path / "ok.yaml"
    ok.write_text("min_items: 3\npass_rate: 0.9\nsafety_tags: [x]\n")
    policy, source = ec.load_policy(ok)
    assert policy.min_items == 3
    assert policy.pass_rate == 0.9
    assert source == f"file:{ok}"

    bad = tmp_path / "bad.yaml"
    bad.write_text("pass_rate: banana\n")
    with pytest.raises(ec.PolicyError):
        ec.load_policy(bad)


def test_load_policy_defaults_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    policy, source = ec.load_policy(None)
    assert policy == ec.Policy()
    assert source == "defaults"

    (tmp_path / ".opik").mkdir()
    (tmp_path / ".opik" / "opik-release-policy.yaml").write_text("min_items: 2\n")
    policy, source = ec.load_policy(None)
    assert policy.min_items == 2
    assert source.startswith("file:")


def test_render_markdown_has_marker_and_caps_rows() -> None:
    rows = [row(f"i{n}", f"s{n}", {"B": [_ok()], "C": [_bad("a")]}) for n in range(30)]
    cmp = _classify(rows)
    verdict = ec.evaluate_policy(cmp, ec.Policy())
    meta = _meta(trace_url=lambda tid: f"http://t/{tid}")
    md = ec.render_markdown(cmp, verdict, meta)
    lines = md.splitlines()
    assert lines[0] == "<!-- opik-eval -->"
    assert "## Opik eval: cand" in md
    assert "**Verdict:** hold" in md
    assert "Pass rate: 1.00 -> 0.00 (-1.00)" in md
    assert "- s0: a ([trace](http://t/t-i0-C-0))" in md
    assert md.count("- s") == 25
    assert "+5 more" in md
    assert "| metric | baseline | candidate | delta |" in md
    assert "http://x/compare" in md
    md.encode("ascii")

    data = ec.render_json(cmp, verdict, meta)
    json.dumps(data)
    assert data["status"] == "hold"
    assert len(data["newly_failing"]) == 30
    assert data["pass_rate"]["delta"] == -1.0
    assert data["meta"]["policy_source"] == "defaults"


def test_render_markdown_groups_still_failing_by_metric() -> None:
    rows = [
        row("i1", "s1", {"B": [_bad()], "C": [_bad("a")]}),
        row("i2", "s2", {"B": [_bad()], "C": [_bad("a")]}),
    ]
    cmp = _classify(rows)
    md = ec.render_markdown(cmp, ec.evaluate_policy(cmp, ec.Policy()), _meta())
    assert "- **a**\n  - s1\n  - s2" in md
    assert "Newly failing\n\nnone" in md


def test_compare_url_encodes_both_ids() -> None:
    url = ec.compare_url("https://h/", "ws", "ds1", ["e1", "e2"])
    assert url == ("https://h/opik/ws/experiments/ds1/compare?experiments=%5B%22e1%22%2C%20%22e2%22%5D")


def test_failing_row_without_reason_is_not_rendered_as_passed() -> None:
    no_reason = [_score(PASS, 0.0, None)]
    rows = [row("i1", "s1", {"B": [_ok()], "C": [no_reason]})]
    cmp = _classify(rows)
    md = ec.render_markdown(cmp, ec.evaluate_policy(cmp, ec.Policy()), _meta())
    assert "- s1: failed (no reason)" in md
    assert "s1: passed" not in md


def test_unscored_candidate_run_does_not_create_a_baseline() -> None:
    # Every candidate run lacks the pass score (metric errors tolerated by evaluate()).
    rows = [row(f"i{n}", f"s{n}", {"C": [[_score("other", 1.0)]]}) for n in range(3)]
    cmp = _classify(rows, baseline_id=None)
    assert cmp.items_unscored == 3
    verdict = ec.evaluate_policy(cmp, ec.Policy(min_items=1), mark_baseline=True)
    assert verdict.status == "insufficient_evidence"
    scored = _classify([row("i9", "s9", {"C": [_ok()]})], baseline_id=None)
    assert scored.items_unscored == 0
    assert ec.evaluate_policy(scored, ec.Policy(min_items=1), mark_baseline=True).status == "baseline_created"


def test_flaky_exclude_drops_flaky_items_from_pass_rate() -> None:
    rows = [row(f"i{n}", f"s{n}", {"B": [_ok()] * 3, "C": [_ok()] * 3}) for n in range(9)]
    rows.append(row("i9", "s9", {"B": [_ok()] * 3, "C": [_ok(), _bad(), _ok()]}))
    cmp = _classify(rows)
    assert len(cmp.flaky) == 1
    excluded = ec.evaluate_policy(cmp, ec.Policy(min_items=1))
    assert excluded.status == "ok", [c for c in excluded.criteria if not c.passed]
    rate = next(c for c in excluded.criteria if c.name == "pass_rate")
    assert rate.observed == "1.00"
    counted = ec.evaluate_policy(cmp, ec.Policy(min_items=1, flaky_policy="count"))
    assert counted.status == "hold"


def test_still_failing_more_counts_items_not_metric_rows() -> None:
    both = [_score(PASS, 0.0, "failed: a 0.35 < 0.90; b 0.35 < 0.90")]
    rows = [row(f"i{n}", f"s{n}", {"B": [_bad()], "C": [both]}) for n in range(30)]
    cmp = _classify(rows)
    md = ec.render_markdown(cmp, ec.evaluate_policy(cmp, ec.Policy()), _meta())
    assert "+5 more" in md
    assert "+35 more" not in md
