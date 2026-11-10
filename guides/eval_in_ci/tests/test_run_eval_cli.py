"""CLI wiring tests for run_eval (no network)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fake_hooks
import pytest
from test_compare import _bad, _ok, row

import run_eval
from eval_compare import MARKER
from opik_access import ConfigError
from run_eval import main


def test_parser_run_requires_dataset_and_task() -> None:
    parser = run_eval.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["run", "--dataset", "d"])
    assert exc.value.code == 2
    args = parser.parse_args(["run", "--dataset", "d", "--task", "m:f", "--metric", "m:b"])
    assert args.project is None
    assert args.label_key == "scenario_id"
    assert args.prompt_name == "scenario-planner"
    args = parser.parse_args(["run", "--dataset", "d", "--project", "p", "--task", "m:f", "--metric", "m:b"])
    assert args.metric == "m:b"
    assert args.trials == 1
    assert args.mark_baseline is False


def test_run_config_error_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> Any:
        raise ConfigError("Set OPIK_API_KEY and OPIK_WORKSPACE")

    monkeypatch.setattr(run_eval.opik_access, "make_client", boom)
    code = run_eval.main(["run", "--dataset", "d", "--project", "p", "--task", "m:f", "--metric", "m:b"])
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


CANDIDATE = "exp-1"
_DEFAULT = object()


class StubClient:
    """Opik client stand-in that records every write the run makes."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.dataset = SimpleNamespace(id="ds")
        self.baseline: Any = SimpleNamespace(id="B", name="base", tags=["baseline"])
        self.production: Any = None
        self.history: list[Any] = []
        self.environments: list[str] = ["production"]
        self.environments_created: list[str] = []
        self.suite_result = SimpleNamespace(items_passed=8, items_total=8)
        self.tags_added: list[tuple[str, list[str]]] = []
        self.environments_set: list[tuple[str, list[str], str]] = []
        self.prompts_created: list[dict[str, Any]] = []
        self.traffic_calls = 0
        self.evaluate_calls: list[dict[str, Any]] = []
        self.run_tests_calls: list[dict[str, Any]] = []
        experiments = SimpleNamespace(
            find_experiments=lambda **_k: SimpleNamespace(content=[self.baseline] if self.baseline else []),
            update_experiment=lambda id, tags_to_add: self.tags_added.append((id, tags_to_add)),
        )
        datasets = SimpleNamespace(
            find_dataset_items_with_experiment_items=lambda **_k: SimpleNamespace(
                content=self.rows, total=len(self.rows)
            )
        )
        self.rest_client = SimpleNamespace(
            experiments=experiments, datasets=datasets, version=lambda: {"version": "9.9.9"}
        )

    def get_dataset(self, name: str) -> Any:
        return self.dataset

    def create_prompt(self, **kwargs: Any) -> Any:
        self.prompts_created.append(kwargs)
        return SimpleNamespace(name=kwargs["name"], version="v1", prompt=kwargs["prompt"], environments=[])

    def get_prompt(self, name: str, **_k: Any) -> Any:
        return self.production

    def get_prompt_history(self, name: str) -> list[Any]:
        return self.history

    def get_environments(self) -> list[Any]:
        return [SimpleNamespace(name=n) for n in self.environments]

    def create_environment(self, name: str, **_k: Any) -> None:
        self.environments.append(name)
        self.environments_created.append(name)

    def set_prompt_environments(self, name: str, environments: list[str], version: str) -> None:
        self.environments_set.append((name, environments, version))

    def get_test_suite(self, name: str) -> Any:
        return SimpleNamespace(name=name)


def _rows(candidate: Any = _ok, n: int = 10) -> list[Any]:
    return [row(f"i{i}", f"s{i}", {"B": [_ok()], CANDIDATE: [candidate()]}) for i in range(n)]


def _install(monkeypatch: pytest.MonkeyPatch, client: StubClient) -> StubClient:
    fake_hooks.FACTORY_CALLS.clear()
    fake_hooks.SUITE_FACTORY_CALLS.clear()
    monkeypatch.setattr(run_eval.opik_access, "make_client", lambda: client)
    monkeypatch.setattr(run_eval.opik_access, "ui_base_and_workspace", lambda c: ("https://h/", "ws"))

    def fake_evaluate(**kwargs: Any) -> Any:
        client.evaluate_calls.append(kwargs)
        return SimpleNamespace(experiment_id=CANDIDATE)

    def fake_run_tests(suite: Any, task: Any, **kwargs: Any) -> Any:
        client.run_tests_calls.append({"suite": suite, "task": task, **kwargs})
        return client.suite_result

    monkeypatch.setattr(run_eval, "evaluate", fake_evaluate)
    monkeypatch.setattr(run_eval, "run_tests", fake_run_tests)
    return client


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> StubClient:
    client = _install(monkeypatch, StubClient(_rows()))
    client.tmp_path = tmp_path  # type: ignore[attr-defined]
    return client


@pytest.fixture
def stub_all_unscored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> StubClient:
    client = _install(monkeypatch, StubClient(_rows(candidate=list)))
    client.tmp_path = tmp_path  # type: ignore[attr-defined]
    return client


def _run_args(
    stub: StubClient,
    *,
    prompt_file: Any = _DEFAULT,
    out: Path | None = None,
    mark_baseline: bool = False,
    suite: bool = False,
    traffic: bool | str = False,
    fail_on_regression: bool = False,
    policy: Path | None = None,
    extra: tuple[str, ...] = (),
    setup: bool = False,
    label_key: str | None = None,
    summary: Path | None = None,
) -> list[str]:
    args = ["run", "--dataset", "d", "--task", "fake_hooks:make_task", "--metric", "fake_hooks:metric"]
    if prompt_file is _DEFAULT:
        prompt_file = stub.tmp_path / "system.txt"  # type: ignore[attr-defined]
    if prompt_file is not None:
        if not prompt_file.exists():
            prompt_file.write_text("You plan driving scenarios.\n", encoding="utf-8")
        args += ["--prompt-file", str(prompt_file)]
    if out:
        args += ["--out", str(out)]
    if mark_baseline:
        args.append("--mark-baseline")
    if suite:
        args += ["--suite-task", "fake_hooks:make_suite_task", "--suite-name", "guardrails"]
    if traffic:
        args += ["--traffic", traffic if isinstance(traffic, str) else "fake_hooks:traffic"]
    if fail_on_regression:
        args.append("--fail-on-regression")
    if policy:
        args += ["--policy", str(policy)]
    if setup:
        args += ["--setup", "fake_hooks:setup"]
    if label_key:
        args += ["--label-key", label_key]
    if summary:
        args += ["--summary", str(summary)]
    return args + list(extra)


def test_run_logs_prompt_and_names_version_in_digest(stub: StubClient, tmp_path: Path) -> None:
    rc = main(_run_args(stub, prompt_file=tmp_path / "p.txt", out=tmp_path / "d.md"))
    assert rc == 0 and "Prompt: scenario-planner v1" in (tmp_path / "d.md").read_text()
    [created] = stub.prompts_created
    assert created["name"] == "scenario-planner"
    assert created["change_description"].startswith("ci ")
    assert stub.evaluate_calls[0]["prompts"][0].version == "v1"


def test_run_marks_unchanged_prompt(stub: StubClient, tmp_path: Path) -> None:
    stub.production = SimpleNamespace(
        name="scenario-planner", version="v1", prompt="You plan driving scenarios.\n", environments=[]
    )
    main(_run_args(stub, out=tmp_path / "d.md"))
    assert "Prompt: scenario-planner v1 (unchanged)" in (tmp_path / "d.md").read_text()
    assert stub.prompts_created == []


def test_run_without_prompt_file_says_not_tracked(stub: StubClient, tmp_path: Path) -> None:
    assert main(_run_args(stub, prompt_file=None, out=tmp_path / "d.md")) == 0
    assert "Prompt: not tracked" in (tmp_path / "d.md").read_text()
    assert stub.prompts_created == []
    assert stub.evaluate_calls[0]["prompts"] is None


def test_pr_run_never_tags_or_promotes(stub: StubClient) -> None:
    assert main(_run_args(stub)) == 0
    assert stub.tags_added == [] and stub.environments_set == []
    assert "candidate" in stub.evaluate_calls[0]["experiment_tags"]


def test_mark_baseline_tags_and_promotes(stub: StubClient, tmp_path: Path) -> None:
    main(_run_args(stub, mark_baseline=True, out=tmp_path / "d.md"))
    assert stub.tags_added == [("exp-1", ["baseline"])]
    assert stub.environments_set == [("scenario-planner", ["production"], "v1")]
    md = (tmp_path / "d.md").read_text()
    assert md.startswith(MARKER)
    assert "Promoted to production: scenario-planner v1" in md
    assert "Warning:" not in md
    assert "baseline" not in stub.evaluate_calls[0]["experiment_tags"]


def test_mark_baseline_without_evidence_does_neither(
    stub_all_unscored: StubClient, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_run_args(stub_all_unscored, mark_baseline=True)) == 0
    assert stub_all_unscored.tags_added == []
    assert stub_all_unscored.environments_set == []
    assert "not tagged" in capsys.readouterr().err


def test_mark_baseline_with_failed_suite_promotes_and_warns(stub: StubClient, tmp_path: Path) -> None:
    stub.suite_result = SimpleNamespace(items_passed=6, items_total=8)
    main(_run_args(stub, mark_baseline=True, suite=True, out=tmp_path / "d.md"))
    md = (tmp_path / "d.md").read_text().splitlines()
    assert md[0] == MARKER
    assert md[2].startswith("Warning: promoted with failed criteria: test_suite")
    assert "Test suite: 6 of 8 passed" in md
    assert stub.environments_set  # promoted anyway


def test_pr_run_with_failed_suite_holds(stub: StubClient) -> None:
    stub.suite_result = SimpleNamespace(items_passed=6, items_total=8)
    assert main(_run_args(stub, suite=True, fail_on_regression=True)) == 1
    [call] = stub.run_tests_calls
    assert call["experiment_name"].endswith("-suite")
    assert call["suite"].name == "guardrails"


def test_empty_suite_is_a_config_error(stub: StubClient, capsys: pytest.CaptureFixture[str]) -> None:
    stub.suite_result = SimpleNamespace(items_passed=0, items_total=0)
    assert main(_run_args(stub, suite=True, mark_baseline=True)) == 2
    assert "Test suite guardrails has no items" in capsys.readouterr().err
    assert stub.tags_added == []


def test_traffic_runs_only_after_promotion(stub: StubClient) -> None:
    main(_run_args(stub, traffic=True))  # PR run
    assert stub.traffic_calls == 0
    main(_run_args(stub, traffic=True, mark_baseline=True))  # main run
    assert stub.traffic_calls == 1


def test_traffic_note_links_logs_of_setup_project(stub: StubClient, tmp_path: Path) -> None:
    main(_run_args(stub, traffic=True, mark_baseline=True, setup=True, out=tmp_path / "d.md"))
    md = (tmp_path / "d.md").read_text()
    assert (
        "Sent 6 production requests; online rule scores them in Logs: "
        "https://h/opik/ws/projects/proj-setup/logs"
    ) in md


def test_traffic_failure_after_promotion_says_what_was_done(stub: StubClient, tmp_path: Path) -> None:
    summary = tmp_path / "s.md"
    args = _run_args(stub, traffic="fake_hooks:broken_traffic", mark_baseline=True, summary=summary)
    assert main(args) == 2
    text = summary.read_text()
    assert "model provider down" in text
    assert "Promoted to production: scenario-planner v1" in text
    assert "Nothing was tagged" not in text


def test_task_factory_receives_prompt_text(stub: StubClient, tmp_path: Path) -> None:
    prompt = tmp_path / "p.txt"
    prompt.write_text("Plan it.\n", encoding="utf-8")
    main(_run_args(stub, prompt_file=prompt, suite=True))
    assert fake_hooks.FACTORY_CALLS == ["Plan it.\n"]
    assert fake_hooks.SUITE_FACTORY_CALLS == ["Plan it.\n"]
    item = {"id": "item-1", "input": "x"}
    assert stub.evaluate_calls[0]["task"](item) == {"output": item}


def test_setup_hook_dataset_is_used(stub: StubClient) -> None:
    stub.dataset = SimpleNamespace(id="ds-setup")
    stub.get_dataset = None  # type: ignore[assignment,method-assign]
    assert main(_run_args(stub, setup=True)) == 0
    assert stub.evaluate_calls[0]["dataset"].id == "ds-setup"


def test_policy_required_without_suite_task_exits_2(stub: StubClient, tmp_path: Path) -> None:
    (tmp_path / "p.yaml").write_text("test_suite: required\n")
    assert main(_run_args(stub, policy=tmp_path / "p.yaml")) == 2
    assert stub.evaluate_calls == []
    assert stub.prompts_created == []


def test_digest_names_policy_source(
    stub: StubClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    main(_run_args(stub, out=tmp_path / "d.md"))
    assert "Policy: defaults" in (tmp_path / "d.md").read_text()
    (tmp_path / "p.yaml").write_text("min_items: 1\n")
    main(_run_args(stub, policy=tmp_path / "p.yaml", out=tmp_path / "d.md"))
    assert f"Policy: file:{tmp_path / 'p.yaml'}" in (tmp_path / "d.md").read_text()


def test_label_key_names_rows(stub: StubClient, tmp_path: Path) -> None:
    stub.rows = _rows(candidate=_bad, n=1)
    stub.rows[0].data["question"] = "what now"
    main(_run_args(stub, label_key="question", out=tmp_path / "d.md"))
    assert "- what now: a" in (tmp_path / "d.md").read_text()


def test_run_task_crash_exits_2_without_dry_run_hint(
    stub: StubClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def boom(**_k: Any) -> Any:
        raise KeyError("missing")

    monkeypatch.setattr(run_eval, "evaluate", boom)
    monkeypatch.setattr(run_eval.config, "DRY_RUN", True)
    summary = tmp_path / "s.md"
    assert main([*_run_args(stub, mark_baseline=True), "--summary", str(summary)]) == 2
    err = capsys.readouterr().err
    assert "Task or metric error" in err
    assert "opik configure" not in err
    text = summary.read_text(encoding="utf-8")
    assert "Failed:" in text and "Task or metric error" in text
    assert stub.tags_added == []


def _demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)


def test_demo_exits_zero_without_example_task(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _demo_env(monkeypatch)
    assert main(["demo", "--out", str(tmp_path / "d.md")]) == 0
    md = (tmp_path / "d.md").read_text()
    assert "0.00 -> 0.60" in md
    assert "Prompt: prompts/system.txt (demo, not logged)" in md
    assert "example_task" not in sys.modules
    assert 'Demo exit code is always 0. In CI, use "run --fail-on-regression"' in capsys.readouterr().out


def test_demo_json_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _demo_env(monkeypatch)
    target = tmp_path / "digest.json"
    assert main(["demo", "--json", str(target)]) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["pass_rate"]["baseline"] == 0.0
    assert payload["pass_rate"]["candidate"] == pytest.approx(0.6)
    assert payload["meta"]["baseline_name"] == "local-weak"
    assert payload["meta"]["candidate_name"] == "local-system"
    assert payload["newly_failing"] == []
    assert len(payload["newly_passing"]) == 12
    assert sorted(o["dataset_item_id"] for o in payload["still_failing"]) == [f"s{i}" for i in range(13, 21)]


def test_run_without_credentials_exits_2_pointing_to_demo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> Any:
        raise ConfigError("Set OPIK_API_KEY and OPIK_WORKSPACE")

    monkeypatch.setattr(run_eval.opik_access, "make_client", boom)
    monkeypatch.setattr(run_eval.config, "DRY_RUN", True)
    assert run_eval.main(["run", "--dataset", "d", "--task", "m:f", "--metric", "m:b"]) == 2
    err = capsys.readouterr().err
    assert "demo" in err
    assert "opik configure" in err


def test_build_digest_links_traces_to_candidate_project(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [row("i1", "s1", {"B": [_ok()], "C": [_bad("a")]}, projects={"B": "proj-base", "C": "proj-cand"})]
    monkeypatch.setattr(run_eval.opik_access, "fetch_compare_rows", lambda c, d, ids: rows)
    monkeypatch.setattr(run_eval.opik_access, "ui_base_and_workspace", lambda c: ("https://h/", "ws"))
    md, _ = run_eval._build_digest(
        None, "ds", "B", "base", "C", "cand", pass_threshold=None, policy_path=None, git={}, version=None
    )
    assert "projects/proj-cand/traces?trace=t-i1-C-0" in md
    assert "proj-base" not in md


def test_run_requires_metric() -> None:
    with pytest.raises(SystemExit) as e:
        run_eval.build_parser().parse_args(["run", "--dataset", "d", "--task", "m:t"])
    assert e.value.code == 2


def test_suite_flags_must_pair(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("OPIK_API_KEY", "k")
    monkeypatch.setenv("OPIK_WORKSPACE", "w")
    args = ["run", "--dataset", "d", "--task", "m:t", "--metric", "m:b"]
    assert run_eval.main([*args, "--suite-task", "m:s"]) == 2
    assert "--suite-name" in capsys.readouterr().err
    assert run_eval.main([*args, "--suite-name", "n"]) == 2
    assert "--suite-task" in capsys.readouterr().err


def test_config_error_writes_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPIK_API_KEY", raising=False)
    monkeypatch.delenv("OPIK_WORKSPACE", raising=False)

    def boom() -> Any:
        raise ConfigError("no creds")

    monkeypatch.setattr(run_eval.opik_access, "make_client", boom)
    summary = tmp_path / "s.md"
    assert run_eval.main(["digest", "--experiment", "x", "--summary", str(summary)]) == 2
    assert "Failed:" in summary.read_text(encoding="utf-8")


def test_suite_judge_uses_suite_model_and_writes_no_report(stub: StubClient) -> None:
    main(_run_args(stub, suite=True))
    [call] = stub.run_tests_calls
    assert call["model"] == run_eval.config.GEN_MODEL
    assert call["generate_report"] is False
    main(_run_args(stub, suite=True, extra=("--suite-model", "openai/gpt-4o-mini")))
    assert stub.run_tests_calls[-1]["model"] == "openai/gpt-4o-mini"


def test_missing_suite_is_a_config_error(stub: StubClient, capsys: pytest.CaptureFixture[str]) -> None:
    stub.get_test_suite = lambda name: None  # type: ignore[method-assign]
    assert main(_run_args(stub, suite=True)) == 2
    assert "Test suite 'guardrails'" in capsys.readouterr().err


def test_mark_baseline_without_setup_creates_production_environment(stub: StubClient) -> None:
    stub.environments = []
    main(_run_args(stub, mark_baseline=True))
    assert stub.environments_created == ["production"]
    assert stub.environments_set == [("scenario-planner", ["production"], "v1")]


def test_pass_score_flag_names_the_gate_score(stub: StubClient, tmp_path: Path) -> None:
    def custom() -> list[dict[str, Any]]:
        return [{"name": "my_pass", "value": 1.0, "reason": None}]

    stub.rows = [row(f"i{i}", f"s{i}", {CANDIDATE: [custom()]}) for i in range(10)]
    stub.baseline = None
    main(_run_args(stub, mark_baseline=True, extra=("--pass-score", "my_pass"), out=tmp_path / "d.md"))
    assert stub.tags_added == [("exp-1", ["baseline"])]
    stub.tags_added.clear()
    main(_run_args(stub, mark_baseline=True, out=tmp_path / "d.md"))
    assert stub.tags_added == []


def test_mark_baseline_without_evidence_warns_in_digest(
    stub_all_unscored: StubClient, tmp_path: Path
) -> None:
    main(_run_args(stub_all_unscored, mark_baseline=True, out=tmp_path / "d.md"))
    lines = (tmp_path / "d.md").read_text().splitlines()
    assert lines[2] == "Warning: baseline not created: no item carried the pass score 'scenario_pass'"


def test_digest_accepts_pass_score(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    _stub_digest(monkeypatch, "ok")
    monkeypatch.setattr(
        run_eval, "_build_digest", lambda *a, **k: seen.update(k) or ("# d", {"status": "ok"})
    )
    assert run_eval.main(["digest", "--experiment", "cand", "--pass-score", "my_pass"]) == 0
    assert seen["pass_name"] == "my_pass"


def test_traffic_skipped_without_tracked_prompt(stub: StubClient, tmp_path: Path) -> None:
    main(_run_args(stub, prompt_file=None, traffic=True, mark_baseline=True, out=tmp_path / "d.md"))
    assert stub.traffic_calls == 0
    assert "Traffic not sent: no prompt was tracked (--prompt-file)" in (tmp_path / "d.md").read_text()
