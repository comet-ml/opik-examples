import os
import subprocess
import sys
from pathlib import Path
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
    results = build_metric(track=False).score(expected=item["expected"], **output)
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


def test_build_metric_tracks_by_default() -> None:
    assert build_metric().track is True
    assert build_metric(track=False).track is False


def test_script_dry_runs_without_credentials() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("OPIK_API_KEY", "OPIK_WORKSPACE")}
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "example_task.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("[DRY RUN] would insert 12 items")
    assert "s12" in proc.stdout
