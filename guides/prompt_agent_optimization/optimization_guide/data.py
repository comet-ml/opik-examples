import json
from typing import Any

from . import config


def _load(name: str) -> list[dict]:
    return json.loads((config.DATA_DIR / name).read_text())


def load_docs() -> list[dict]:
    return _load("docs.json")


def load_exact_cases() -> list[dict]:
    return _load("eval_cases_exact.json")


def load_judge_cases() -> list[dict]:
    return _load("eval_cases_judge.json")


def build_dataset(client: Any, name: str, cases: list[dict]) -> Any:
    """Get-or-create an Opik dataset and insert cases.

    Opik dedups identical items on insert, so re-running is safe (idempotent).
    """
    dataset = client.get_or_create_dataset(name)
    dataset.insert(cases)
    return dataset
