"""Tests for the optimizer metric adapter (the optimizer itself is not run)."""

import json
from typing import Any

from example_task import SCENARIOS
from optimize_prompt import composite_metric_adapter


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
