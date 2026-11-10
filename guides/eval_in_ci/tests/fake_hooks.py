"""module:callable hooks the run_eval CLI tests load by reference (no network)."""

from types import SimpleNamespace
from typing import Any

FACTORY_CALLS: list[str | None] = []
SUITE_FACTORY_CALLS: list[str | None] = []


def make_task(prompt_text: str | None) -> Any:
    FACTORY_CALLS.append(prompt_text)
    return lambda item: {"output": item}


def make_suite_task(prompt_text: str | None) -> Any:
    SUITE_FACTORY_CALLS.append(prompt_text)
    return lambda item: {"input": item["input"], "output": "{}"}


def metric() -> Any:
    return object()


def setup(client: Any) -> Any:
    return SimpleNamespace(dataset=client.dataset, project_id="proj-setup")


def traffic(client: Any, prompt_name: str) -> int:
    client.traffic_calls += 1
    return 6


def broken_traffic(client: Any, prompt_name: str) -> int:
    raise RuntimeError("model provider down")
