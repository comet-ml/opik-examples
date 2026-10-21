"""CLI wiring tests for run_eval (no network)."""

import json
from pathlib import Path
from typing import Any

import pytest

import run_eval
from opik_access import ConfigError


def test_parser_run_requires_dataset_and_task() -> None:
    parser = run_eval.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["run", "--dataset", "d"])
    assert exc.value.code == 2
    args = parser.parse_args(["run", "--dataset", "d", "--task", "m:f"])
    assert args.project is None
    args = parser.parse_args(["run", "--dataset", "d", "--project", "p", "--task", "m:f"])
    assert args.metric == "example_task:build_metric"
    assert args.trials == 1
    assert args.mark_baseline is False


def test_run_config_error_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> Any:
        raise ConfigError("Set OPIK_API_KEY and OPIK_WORKSPACE")

    monkeypatch.setattr(run_eval.opik_access, "make_client", boom)
    code = run_eval.main(["run", "--dataset", "d", "--project", "p", "--task", "m:f"])
    assert code == 2
    assert "OPIK_API_KEY" in capsys.readouterr().err


def _stub_digest(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    class Stub:
        pass

    monkeypatch.setattr(run_eval.opik_access, "make_client", lambda: Stub())
    monkeypatch.setattr(run_eval.opik_access, "server_version", lambda c: "9.9.9")
    monkeypatch.setattr(run_eval.opik_access, "find_baseline", lambda c, d, exclude_id=None: None)
    exp = type("Exp", (), {"id": "e1", "name": "cand", "dataset_id": "ds"})()
    monkeypatch.setattr(run_eval.opik_access, "resolve_experiment", lambda c, n, p: exp)

    def fake_build(*_a: Any, **_k: Any) -> tuple[str, dict[str, Any]]:
        return "# digest", {"status": status}

    monkeypatch.setattr(run_eval, "_build_digest", fake_build)


def test_digest_hold_with_fail_flag_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_digest(monkeypatch, "hold")
    code = run_eval.main(["digest", "--experiment", "cand", "--fail-on-regression"])
    assert code == 1
    assert "# digest" in capsys.readouterr().out


def test_digest_hold_without_fail_flag_exits_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_digest(monkeypatch, "hold")
    assert run_eval.main(["digest", "--experiment", "cand"]) == 0


def _stub_run(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    marked: list[Any] = []
    ds = type("DS", (), {"id": "ds"})()
    client = type("C", (), {"get_dataset": lambda self, n: ds})()
    monkeypatch.setattr(run_eval.opik_access, "make_client", lambda: client)
    monkeypatch.setattr(run_eval.opik_access, "server_version", lambda c: "9.9.9")
    monkeypatch.setattr(run_eval.opik_access, "load_callable", lambda ref: lambda: None)
    monkeypatch.setattr(run_eval.opik_access, "mark_baseline", lambda c, eid: marked.append(eid))
    return marked


def test_run_task_crash_exits_2_with_label(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    marked = _stub_run(monkeypatch)

    def boom(**_k: Any) -> Any:
        raise KeyError("missing")

    monkeypatch.setattr(run_eval, "evaluate", boom)
    code = run_eval.main(["run", "--dataset", "d", "--task", "m:f", "--mark-baseline"])
    assert code == 2
    assert "Task or metric error" in capsys.readouterr().err
    assert marked == []


def test_run_mark_baseline_tags_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marked = _stub_run(monkeypatch)
    seen: dict[str, Any] = {}

    def fake_eval(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return type("R", (), {"experiment_id": "e9"})()

    monkeypatch.setattr(run_eval, "evaluate", fake_eval)
    monkeypatch.setattr(
        run_eval,
        "_build_digest",
        lambda *a, **k: ("# d", {"status": "baseline_created"}),
    )
    assert run_eval.main(["run", "--dataset", "d", "--task", "m:f", "--mark-baseline"]) == 0
    assert "baseline" not in seen["experiment_tags"]
    assert marked == ["e9"]


def _demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)


def test_demo_prints_three_sections_offline(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _demo_env(monkeypatch)
    assert run_eval.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert 'Demo exit code is always 0. In CI, use "run --fail-on-regression"' in out
    for text in ("Newly failing", "s05", "Newly passing", "s03", "s07", "0.75 -> 0.83"):
        assert text in out


def test_demo_json_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _demo_env(monkeypatch)
    target = tmp_path / "digest.json"
    assert run_eval.main(["demo", "--json", str(target)]) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["pass_rate"]["baseline"] == 0.75
    assert payload["pass_rate"]["candidate"] == pytest.approx(0.8333, abs=1e-3)
    assert [o["dataset_item_id"] for o in payload["newly_failing"]] == ["s05"]
    assert sorted(o["dataset_item_id"] for o in payload["newly_passing"]) == ["s03", "s07"]


def test_run_without_credentials_exits_2_pointing_to_demo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> Any:
        raise ConfigError("Set OPIK_API_KEY and OPIK_WORKSPACE")

    monkeypatch.setattr(run_eval.opik_access, "make_client", boom)
    monkeypatch.setattr(run_eval, "DRY_RUN", True)
    assert run_eval.main(["run", "--dataset", "d", "--task", "m:f"]) == 2
    err = capsys.readouterr().err
    assert "demo" in err
    assert "opik configure" in err
