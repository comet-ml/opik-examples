"""Tests for the optimize-prompt step: metric adapter, starting prompt and CLI wiring (optimizer stubbed)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import config
import optimize_prompt
from scenarios import SCENARIOS


def _by_name(results: list[Any]) -> dict[str, Any]:
    return {r.name: r for r in results}


def _messages_prompt(system: str) -> SimpleNamespace:
    """Stand-in for an optimizer ChatPrompt, read through get_messages()."""
    return SimpleNamespace(
        get_messages=lambda: [{"role": "system", "content": system}, {"role": "user", "content": "{input}"}]
    )


def test_adapter_scores_fenced_json() -> None:
    item = SCENARIOS[0]
    text = f"```json\n{json.dumps(item['expected'])}\n```"
    assert _by_name(optimize_prompt.composite_metric_adapter(item, text))["scenario_pass"].value == 1.0
    assert optimize_prompt.composite_metric_adapter.__name__ == "scenario_pass"


def test_adapter_invalid_text_fails_cleanly() -> None:
    results = _by_name(optimize_prompt.composite_metric_adapter(SCENARIOS[0], "nope"))
    assert results["scenario_pass"].value == 0.0


def test_best_system_text_requires_single_system_prompt() -> None:
    ok = SimpleNamespace(prompt=_messages_prompt("Better prompt"))
    assert optimize_prompt.best_system_text(ok) == "Better prompt"
    no_system = SimpleNamespace(get_messages=lambda: [{"role": "user", "content": "{input}"}])
    for bad in (SimpleNamespace(prompt={"a": ok.prompt}), SimpleNamespace(prompt=no_system)):
        with pytest.raises(optimize_prompt.ConfigError):
            optimize_prompt.best_system_text(bad)


def test_best_system_text_reads_messages_prompt() -> None:
    # WHY: MetaPromptOptimizer builds candidates with ChatPrompt(messages=...), which leaves .system None.
    opt = pytest.importorskip("opik_optimizer")
    prompt = opt.ChatPrompt(
        messages=[{"role": "system", "content": "Better prompt"}, {"role": "user", "content": "{input}"}]
    )
    assert prompt.system is None
    assert optimize_prompt.best_system_text(SimpleNamespace(prompt=prompt)) == "Better prompt"


def test_missing_optimizer_extra_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opik_optimizer", None)
    with pytest.raises(optimize_prompt.ConfigError, match="uv sync --extra optimizer"):
        optimize_prompt.run_optimizer("SYS", object(), max_trials=1)


def _client(production: str | None) -> SimpleNamespace:
    def get_prompt(name: str, **_k: Any) -> Any:
        return None if production is None else SimpleNamespace(name=name, prompt=production)

    return SimpleNamespace(
        get_prompt=get_prompt, get_dataset=lambda name: SimpleNamespace(id="ds", name=name)
    )


def test_starting_prompt_prefers_production(tmp_path: Path) -> None:
    f = tmp_path / "system.txt"
    f.write_text("FILE\n")
    assert optimize_prompt.starting_prompt(_client("PROD"), "p", f) == "PROD"


def test_starting_prompt_falls_back_to_file(tmp_path: Path) -> None:
    f = tmp_path / "system.txt"
    f.write_text("FILE\n")
    assert optimize_prompt.starting_prompt(_client(None), "p", f) == "FILE"


def test_starting_prompt_without_any_source_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(optimize_prompt.ConfigError):
        optimize_prompt.starting_prompt(_client(None), "p", tmp_path / "missing.txt")


def _stub_live(
    monkeypatch: pytest.MonkeyPatch, *, best: str, production: str | None = None, run_link: bool = True
) -> None:
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(optimize_prompt.opik_access, "make_client", lambda: _client(production))

    def get_run_link() -> str:
        if not run_link:
            raise RuntimeError("no link")
        return "https://h/opt"

    result = SimpleNamespace(
        prompt=_messages_prompt(best), initial_score=0.4, score=0.7, get_run_link=get_run_link
    )
    monkeypatch.setattr(optimize_prompt, "run_optimizer", lambda *_a, **_k: result)


def _args(tmp_path: Path, f: Path) -> list[str]:
    return [
        "--prompt-file",
        str(f),
        "--github-output",
        str(tmp_path / "out.txt"),
        "--summary",
        str(tmp_path / "summary.md"),
        "--json",
        str(tmp_path / "out.json"),
    ]


def test_writes_only_prompt_file_and_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "system.txt"
    f.write_text("OLD\n")
    _stub_live(monkeypatch, best="NEW")
    rc = optimize_prompt.main(_args(tmp_path, f))
    assert rc == 0 and f.read_text() == "NEW\n"
    out = (tmp_path / "out.txt").read_text()
    assert "changed=true" in out and "best_score=0.70" in out and "initial_score=0.40" in out
    assert "run_link=https://h/opt" in out
    summary = (tmp_path / "summary.md").read_text()
    assert "## Optimize prompt" in summary
    assert "Optimizer: initial 0.40 -> best 0.70 ([run](https://h/opt))" in summary
    assert "Prompt file: changed" in summary
    payload = json.loads((tmp_path / "out.json").read_text())
    assert payload["changed"] is True and payload["best_score"] == "0.70"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.json", "out.txt", "summary.md", "system.txt"]


def test_unchanged_prompt_sets_changed_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "system.txt"
    f.write_text("FILE\n")
    _stub_live(monkeypatch, best="PROD", production="PROD\n", run_link=False)
    assert optimize_prompt.main(_args(tmp_path, f)) == 0
    assert f.read_text() == "FILE\n"
    out = (tmp_path / "out.txt").read_text()
    assert "changed=false" in out and "run_link=\n" in out
    summary = (tmp_path / "summary.md").read_text()
    assert "Prompt file: unchanged" in summary
    assert "([run]" not in summary


def test_missing_dataset_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "system.txt"
    f.write_text("FILE\n")
    monkeypatch.setattr(config, "DRY_RUN", False)

    def no_dataset(name: str) -> Any:
        raise RuntimeError("404")

    client = SimpleNamespace(get_prompt=lambda *_a, **_k: None, get_dataset=no_dataset)
    monkeypatch.setattr(optimize_prompt.opik_access, "make_client", lambda: client)
    assert optimize_prompt.main(_args(tmp_path, f)) == 2
    assert config.DATASET_NAME in capsys.readouterr().err
    assert f.read_text() == "FILE\n"


def test_dry_run_without_credentials_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(config, "DRY_RUN", True)

    def boom() -> Any:
        raise AssertionError("dry run must not build a client")

    monkeypatch.setattr(optimize_prompt.opik_access, "make_client", boom)
    f = tmp_path / "system.txt"
    f.write_text("FILE\n")
    assert optimize_prompt.main(["--prompt-file", str(f), "--github-output", str(tmp_path / "out.txt")]) == 0
    assert "[DRY RUN]" in capsys.readouterr().out
    assert (tmp_path / "out.txt").read_text() == "changed=false\n"
    assert f.read_text() == "FILE\n"
