from typing import Any

import pytest

from example_task import (
    SCENARIOS,
    V1_BROKEN,
    V2_FIXED,
    V2_NEWLY_BROKEN,
    build_metric,
    scenario_agent,
)


def composite_value(item: dict[str, Any]) -> float:
    output = scenario_agent(**item)
    results = build_metric().score(expected=item["expected"], **output)
    return next(r.value for r in results if r.name == "scenario_pass")


def broken_ids() -> set[str]:
    return {s["scenario_id"] for s in SCENARIOS if composite_value(s) == 0.0}


def test_twelve_unique_scenarios() -> None:
    assert len(SCENARIOS) == 12
    assert len({s["scenario_id"] for s in SCENARIOS}) == 12


def test_v1_breaks_exactly_the_declared_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_VERSION", "v1")
    assert broken_ids() == set(V1_BROKEN)


def test_v1_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_VERSION", raising=False)
    assert broken_ids() == set(V1_BROKEN)


def test_v2_fixes_two_and_breaks_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_VERSION", "v2")
    assert broken_ids() == (set(V1_BROKEN) - set(V2_FIXED)) | set(V2_NEWLY_BROKEN)
