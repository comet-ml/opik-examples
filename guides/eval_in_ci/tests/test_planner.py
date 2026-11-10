"""Tests for the scenario planner app and simulated traffic, with a fake completion (no network)."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import opik
import pytest

import planner
from config import GEN_MODEL


# WHY: the SDK caches the tracing switch on first use, so flip it at runtime rather than via env.
@pytest.fixture(autouse=True)
def _no_tracing() -> Iterator[None]:
    opik.set_tracing_active(False)
    yield
    opik.set_tracing_active(True)


def _fake_completion(content: str | None, captured: list[dict[str, Any]] | None = None) -> Any:
    def completion(**kwargs: Any) -> SimpleNamespace:
        if captured is not None:
            captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    return completion


def test_plan_text_sends_system_and_user_at_temperature_0() -> None:
    captured: list[dict[str, Any]] = []
    text = planner.plan_text("SYS", "Ego car stops.", completion=_fake_completion("ok", captured))
    assert text == "ok"
    kwargs = captured[0]
    assert kwargs["model"] == GEN_MODEL
    assert kwargs["temperature"] == 0
    assert kwargs["num_retries"] == 3
    assert kwargs["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "Ego car stops."},
    ]


def test_plan_text_none_content_returns_empty_string() -> None:
    assert planner.plan_text("SYS", "x", completion=_fake_completion(None)) == ""


def test_eval_task_parses_output() -> None:
    task = planner.make_eval_task("SYS", completion=_fake_completion('{"actors": ["ego"]}'))
    result = task({"input": "x", "expected": {}})
    assert result["output"] == {"actors": ["ego"]}
    assert result["raw_output"] == '{"actors": ["ego"]}'


def test_suite_task_returns_input_and_raw_output() -> None:
    task = planner.make_suite_task("SYS", completion=_fake_completion("raw text"))
    assert task({"input": "Ego car stops."}) == {"input": "Ego car stops.", "output": "raw text"}


def _prompt_client(seen: list[dict[str, Any]]) -> SimpleNamespace:
    def get_prompt(name: str, **kwargs: Any) -> SimpleNamespace:
        seen.append({"name": name, **kwargs})
        return SimpleNamespace(prompt="SYS", version="v3")

    return SimpleNamespace(get_prompt=get_prompt)


def test_answer_uses_production_environment() -> None:
    seen: list[dict[str, Any]] = []
    result = planner.answer(
        "Ego car stops.",
        "scenario-planner-demo-1",
        client=_prompt_client(seen),
        completion=_fake_completion("p"),
    )
    assert seen == [{"name": "scenario-planner-demo-1", "environment": "production"}]
    assert result == {"plan": "p", "prompt_version": "v3"}


def test_simulate_traffic_counts_and_flushes(monkeypatch: pytest.MonkeyPatch) -> None:
    flushes: list[int] = []
    monkeypatch.setattr(planner.opik, "flush_tracker", lambda: flushes.append(1))
    seen: list[dict[str, Any]] = []
    count = planner.simulate_traffic(
        _prompt_client(seen), "scenario-planner-demo-1", ["a", "b", "c"], completion=_fake_completion("p")
    )
    assert count == 3
    assert len(seen) == 3
    assert flushes == [1]
