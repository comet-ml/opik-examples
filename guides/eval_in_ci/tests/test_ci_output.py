"""Failure handling of ci_output.run_step (no network)."""

from pathlib import Path

import pytest

import ci_output
from eval_compare import PolicyError
from opik_access import ConfigError


def _fail(exc: Exception) -> int:
    raise exc


@pytest.mark.parametrize("exc", [ConfigError("no creds"), PolicyError("bad key")])
def test_config_and_policy_errors_are_terse(exc: Exception, capsys: pytest.CaptureFixture[str]) -> None:
    assert ci_output.run_step(lambda: _fail(exc), title="t", summary=None, outcome=lambda: "") == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and str(exc) in err


def test_other_value_errors_print_a_traceback(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    summary = tmp_path / "s.md"
    code = ci_output.run_step(
        lambda: _fail(ValueError("bad shape")), title="t", summary=summary, outcome=lambda: "Nothing."
    )
    assert code == 2
    assert "Traceback" in capsys.readouterr().err
    assert "Failed: ValueError: bad shape" in summary.read_text(encoding="utf-8")
