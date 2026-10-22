"""Tests for the optimizer metric adapter (the optimizer itself is not run)."""

import json
from typing import Any

import pytest

from example_task import SCENARIOS
from optimize_prompt import DEFAULT_SYSTEM_PROMPT, composite_metric_adapter, main


def _by_name(results: list[Any]) -> dict[str, Any]:
    return {r.name: r for r in results}


def test_valid_json_passes() -> None:
    item = SCENARIOS[0]
    results = _by_name(composite_metric_adapter(item, json.dumps(item["expected"])))
    assert results["scenario_pass"].value == 1.0


def test_wrong_maneuver_fails() -> None:
    item = SCENARIOS[0]
    wrong = {**item["expected"], "maneuver": "unknown"}
    results = _by_name(composite_metric_adapter(item, json.dumps(wrong)))
    assert results["scenario_pass"].value == 0.0
    assert results["maneuver_correct"].value == 0.0


def test_invalid_json_fails_every_metric() -> None:
    results = _by_name(composite_metric_adapter(SCENARIOS[0], "not json"))
    assert results["scenario_pass"].value == 0.0
    assert results["scenario_pass"].reason == "failed: invalid json"
    assert results["n_metrics_failed"].value == 3.0
    for name in ("actors_correct", "maneuver_correct", "parameters_correct"):
        assert results[name].value == 0.0
        assert results[name].reason == "invalid json"


def test_fenced_json_parses() -> None:
    item = SCENARIOS[0]
    fenced = "```json\n" + json.dumps(item["expected"]) + "\n```"
    results = _by_name(composite_metric_adapter(item, fenced))
    assert results["scenario_pass"].value == 1.0


def test_non_object_json_fails() -> None:
    results = _by_name(composite_metric_adapter(SCENARIOS[0], "[1, 2]"))
    assert results["scenario_pass"].value == 0.0


def test_main_dry_runs_without_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)
    assert main(["--max-trials", "2", "--model", "openai/gpt-4o-mini"]) == 0
    out = capsys.readouterr().out
    assert "[DRY RUN]" in out
    assert "2 trials" in out
    assert DEFAULT_SYSTEM_PROMPT in out


def test_adapter_builds_the_metric_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import optimize_prompt

    real = optimize_prompt.build_metric
    calls: list[int] = []

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(optimize_prompt, "build_metric", counting)
    monkeypatch.setattr(optimize_prompt, "_METRIC", None)
    item = SCENARIOS[0]
    composite_metric_adapter(item, json.dumps(item["expected"]))
    composite_metric_adapter(item, json.dumps(item["expected"]))
    assert len(calls) == 1
