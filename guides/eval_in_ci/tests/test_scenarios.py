"""Tests for the scenario dataset, metric, prompts and config validators (no network)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import config
from config import PROMPTS_DIR
from scenarios import PRODUCTION_REQUESTS, SCENARIOS, build_metric, parse_plan


def _prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def test_dataset_size_and_ids() -> None:
    assert 18 <= len(SCENARIOS) <= 22
    ids = [s["scenario_id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids))


def test_every_target_value_is_stated_in_input() -> None:
    for s in SCENARIOS:
        params = s["expected"]["parameters"]
        assert str(params["speed_mps"]) in s["input"], s["scenario_id"]
        assert str(params["gap_m"]) in s["input"], s["scenario_id"]


def test_system_prompt_leaves_headroom() -> None:
    system = _prompt("system.txt")
    unlisted = [s for s in SCENARIOS if s["expected"]["maneuver"] not in system]
    assert len(unlisted) >= 8


# WHY: the guardrail suite asserts every parameter appears in the input; without this sentence the
# model writes speed_mps 0 for a stopping scenario and the production prompt fails its own suite.
def test_system_prompt_keeps_stated_speed_when_stopping() -> None:
    assert "even when the ego stops" in _prompt("system.txt")


# WHY: the optimizer's ChatPrompt formats message templates, so a brace would be read as a variable.
@pytest.mark.parametrize("name", ["weak.txt", "system.txt"])
def test_prompts_have_no_braces(name: str) -> None:
    text = _prompt(name)
    assert "{" not in text
    assert "}" not in text


def test_weak_prompt_has_no_schema() -> None:
    weak = _prompt("weak.txt")
    assert "actors" not in weak
    assert "parameters" not in weak


def test_production_requests_not_in_dataset() -> None:
    assert 5 <= len(PRODUCTION_REQUESTS) <= 8
    inputs = {s["input"] for s in SCENARIOS}
    assert not inputs.intersection(PRODUCTION_REQUESTS)


@pytest.mark.parametrize("text", ['```json\n{"actors": ["ego"]}\n```', 'Plan: {"actors": ["ego"]}'])
def test_parse_plan_extracts_object(text: str) -> None:
    assert parse_plan(text)["actors"] == ["ego"]


@pytest.mark.parametrize("text", ["", "no json", "[1, 2]", "{bad"])
def test_parse_plan_invalid_returns_empty(text: str) -> None:
    assert parse_plan(text) == {}


def test_metric_scores_empty_output_as_failure() -> None:
    results = build_metric(track=False).score(expected=SCENARIOS[0]["expected"], output={})
    by_name = {r.name: r for r in results}
    assert by_name["scenario_pass"].value == 0.0
    for name in ("actors_correct", "maneuver_correct", "parameters_correct"):
        assert by_name[name].value == 0.0
        assert by_name[name].reason


def test_metric_passes_exact_plan() -> None:
    expected = SCENARIOS[0]["expected"]
    results = build_metric(track=False).score(expected=expected, output=dict(expected))
    by_name = {r.name: r for r in results}
    assert by_name["scenario_pass"].value == 1.0


# WHY: the SDK clients read OPIK_PROJECT_NAME themselves; without this, local runs split between
# "Default Project" and the project config.py names.
@pytest.mark.parametrize("value", [None, ""])
def test_config_exports_project_name_when_unset(value: str | None) -> None:
    env = {k: v for k, v in os.environ.items() if k != "OPIK_PROJECT_NAME"}
    if value is not None:
        env["OPIK_PROJECT_NAME"] = value
    out = subprocess.run(
        [sys.executable, "-c", "import os, config; print(os.environ['OPIK_PROJECT_NAME'])"],
        cwd=Path(config.__file__).parent,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "eval-in-ci-example"
