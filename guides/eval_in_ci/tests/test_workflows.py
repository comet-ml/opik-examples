"""Static checks on the gate template, the optimize workflow and the repo selftest (no GitHub calls)."""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "github" / "opik-eval.yml"
OPTIMIZE = ROOT / "github" / "opik-optimize.yml"
SELFTEST = ROOT.parents[1] / ".github" / "workflows" / "eval-in-ci-selftest.yml"
RUN_SH = ROOT / "run.sh"

# WHY: the guide is copied into other repos without the selftest; skip those tests there.
needs_selftest = pytest.mark.skipif(not SELFTEST.is_file(), reason="selftest not next to this guide")

MODE_PUSH_GATE = "${{ github.event_name == 'push' && '--mark-baseline' || '--fail-on-regression' }}"
GATE_ACTIONS = {
    "actions/checkout@v7",
    "dorny/paths-filter@v4",
    "astral-sh/setup-uv@v7",
    "actions/upload-artifact@v7",
    "actions/github-script@v9",
}
HOOK_FLAGS = ("--dataset", "--task", "--metric", "--prompt-file", "--setup", "--suite-task", "--suite-name")


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(data: dict[str, Any]) -> dict[str, Any]:
    # WHY: PyYAML reads the bare key `on` as the boolean True (YAML 1.1).
    return data.get("on", data.get(True))


def _steps(path: Path) -> list[dict[str, Any]]:
    return [s for job in _load(path)["jobs"].values() for s in job.get("steps", [])]


def _step(path: Path, name: str) -> dict[str, Any]:
    (step,) = [s for s in _steps(path) if s.get("name") == name]
    return step


def _envs(path: Path) -> list[dict[str, Any]]:
    data = _load(path)
    envs = [data.get("env") or {}]
    for job in data["jobs"].values():
        envs.append(job.get("env") or {})
        envs.extend(s.get("env") or {} for s in job.get("steps", []))
    return envs


def _flags(text: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z-]+) ([a-z][\w./:-]*)", text))


def test_template_triggers() -> None:
    assert set(_on(_load(TEMPLATE))) == {"pull_request", "push", "workflow_dispatch"}
    assert _on(_load(TEMPLATE))["push"] == {"branches": ["main"]}


@pytest.mark.parametrize("path", [TEMPLATE, OPTIMIZE], ids=["template", "optimize"])
def test_actions_pinned_to_majors(path: Path) -> None:
    uses = [s["uses"] for s in _steps(path) if "uses" in s]
    assert uses
    for ref in uses:
        assert re.search(r"@v\d+$", ref), ref


def test_template_uses_uv_and_current_actions() -> None:
    uses = {s["uses"] for s in _steps(TEMPLATE) if "uses" in s}
    assert uses == GATE_ACTIONS
    setup_uv = next(s for s in _steps(TEMPLATE) if s.get("uses") == "astral-sh/setup-uv@v7")
    assert "version" not in setup_uv["with"]
    assert "pip install" not in "\n".join(s.get("run", "") for s in _steps(TEMPLATE))
    assert "Security-reviewed repos usually pin these to commit SHAs." in TEMPLATE.read_text(encoding="utf-8")


@needs_selftest
def test_selftest_uses_the_template_action_majors() -> None:
    assert {s["uses"] for s in _steps(SELFTEST) if "uses" in s} == GATE_ACTIONS - {"dorny/paths-filter@v4"}


def test_optimize_uses_current_action_majors() -> None:
    assert {s["uses"] for s in _steps(OPTIMIZE) if "uses" in s} == {
        "actions/checkout@v7",
        "astral-sh/setup-uv@v7",
    }
    assert _step(OPTIMIZE, "Optimize the prompt")["env"]["OPIK_PROJECT_NAME"] == "eval-in-ci-example"


def test_template_eval_job_has_timeout() -> None:
    assert _load(TEMPLATE)["jobs"]["eval"]["timeout-minutes"] == 20


def test_template_has_install_your_project_step() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r"^\s*# - name: Install your project$", text, re.M)
    assert re.search(r"^\s*#   working-directory: examples/eval_in_ci$", text, re.M)
    assert re.search(r"^\s*#   run: uv pip install -e \.\./\.\.$", text, re.M)
    assert "installs your repo into the eval project's environment so --task can import it" in text.lower()
    assert "pip install -e ." not in text.replace("uv pip install -e ../..", "")


def test_template_passes_metric_and_prompt_file() -> None:
    run = _step(TEMPLATE, "Run evaluation")["run"]
    assert "uv run python run_eval.py run" in run
    flags = _flags(run)
    assert flags["--metric"] == "scenarios:build_metric"
    assert flags["--prompt-file"] == "prompts/system.txt"
    assert flags["--traffic"] == "planner:simulate_traffic_hook"
    assert '--summary "$GITHUB_STEP_SUMMARY"' in run


def test_template_push_uses_mark_baseline_without_fail_flag() -> None:
    step = _step(TEMPLATE, "Run evaluation")
    assert step["env"]["MODE_FLAG"] == MODE_PUSH_GATE
    assert '"$MODE_FLAG"' in step["run"]
    assert "--fail-on-regression" not in step["run"]
    assert "--mark-baseline" not in step["run"]


def test_template_env_block() -> None:
    env = _step(TEMPLATE, "Run evaluation")["env"]
    assert env["OPIK_PROJECT_NAME"] == "eval-in-ci-example"
    assert env["OPIK_URL_OVERRIDE"] == "${{ vars.OPIK_URL_OVERRIDE || 'https://www.comet.com/opik/api' }}"
    assert env["OPIK_EXAMPLES_MODEL"] == "${{ vars.OPIK_EXAMPLES_MODEL }}"
    assert env["OPIK_ONLINE_JUDGE_MODEL"] == "${{ vars.OPIK_ONLINE_JUDGE_MODEL }}"
    assert env["ANTHROPIC_API_KEY"] == "${{ secrets.ANTHROPIC_API_KEY }}"
    assert env["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert env["OPIK_EVAL_GIT_SHA"] == "${{ github.event.pull_request.head.sha || github.sha }}"


def test_template_guard_paths() -> None:
    guard = _load(TEMPLATE)["jobs"]["guard"]
    filters = next(s for s in guard["steps"] if s.get("uses") == "dorny/paths-filter@v4")["with"]["filters"]
    paths = yaml.safe_load(filters)["eval_paths"]
    assert paths == [
        "examples/eval_in_ci/composite_metric.py",
        "examples/eval_in_ci/scenarios.py",
        "examples/eval_in_ci/setup_opik.py",
        "examples/eval_in_ci/eval_compare.py",
        "examples/eval_in_ci/run_eval.py",
        "examples/eval_in_ci/opik_access.py",
        ".github/workflows/opik-eval.yml",
        "opik-release-policy.yaml",
        ".opik/**",
        "examples/eval_in_ci/opik-release-policy.yaml",
        "examples/eval_in_ci/.opik/**",
    ]
    block = next(s for s in guard["steps"] if "if" in s)["if"]
    # WHY: head_ref is empty on workflow_dispatch, the event that runs the gate on optimize/<n>.
    assert "startsWith(github.head_ref || github.ref_name, 'eval/')" in block
    assert "startsWith(github.head_ref || github.ref_name, 'optimize/')" in block


@pytest.mark.parametrize("path", [TEMPLATE, SELFTEST], ids=["template", "selftest"])
def test_main_runs_are_never_cancelled(path: Path) -> None:
    if not path.is_file():
        pytest.skip("selftest not next to this guide")
    assert _load(path)["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


@pytest.mark.parametrize("path", [TEMPLATE, OPTIMIZE, SELFTEST], ids=["template", "optimize", "selftest"])
def test_no_expressions_inside_run_blocks(path: Path) -> None:
    if not path.is_file():
        pytest.skip("selftest not next to this guide")
    for step in _steps(path):
        assert "${{" not in step.get("run", ""), step.get("name")


@pytest.mark.parametrize("path", [TEMPLATE, OPTIMIZE, SELFTEST], ids=["template", "optimize", "selftest"])
def test_workspace_and_url_are_vars(path: Path) -> None:
    if not path.is_file():
        pytest.skip("selftest not next to this guide")
    text = path.read_text(encoding="utf-8")
    assert "secrets.OPIK_WORKSPACE" not in text
    assert "secrets.OPIK_URL_OVERRIDE" not in text
    assert any(e.get("OPIK_WORKSPACE") == "${{ vars.OPIK_WORKSPACE }}" for e in _envs(path))


def test_run_sh_and_template_share_the_flag_set() -> None:
    template = _flags(_step(TEMPLATE, "Run evaluation")["run"])
    script = _flags(RUN_SH.read_text(encoding="utf-8"))
    for flag in (*HOOK_FLAGS, "--traffic"):
        assert template[flag] == script[flag], flag


@needs_selftest
def test_selftest_smoke_on_pr_showcase_on_main() -> None:
    on = _on(_load(SELFTEST))
    assert set(on) == {"pull_request", "push", "workflow_dispatch"}
    paths = ["guides/eval_in_ci/**", ".github/workflows/eval-in-ci-selftest.yml"]
    assert on["pull_request"]["paths"] == paths
    assert on["push"] == {"branches": ["main"], "paths": paths}
    (job,) = _load(SELFTEST)["jobs"].values()
    assert job["timeout-minutes"] == 20
    assert job["env"]["OPIK_PROJECT_NAME"] == (
        "${{ github.event_name == 'push' && 'eval-in-ci-example' || 'eval-in-ci-smoke' }}"
    )
    step = _step(SELFTEST, "Run evaluation")
    assert step["env"]["MODE_FLAG"] == "${{ github.event_name == 'push' && '--mark-baseline' || '' }}"
    assert "--fail-on-regression" not in SELFTEST.read_text(encoding="utf-8")
    assert 'bash run.sh "$MODE_FLAG"' in step["run"]
    assert '--summary "$GITHUB_STEP_SUMMARY"' in step["run"]
    names = [s.get("name") for s in job["steps"]]
    assert names.index("Unit tests") < names.index("Run evaluation")


@needs_selftest
def test_sticky_comment_script_identical() -> None:
    def script(path: Path) -> str:
        body = _step(path, "Post sticky PR comment")["with"]["script"]
        return body.replace("examples/eval_in_ci/", "").replace("guides/eval_in_ci/", "")

    assert script(SELFTEST) == script(TEMPLATE)
    assert "examples/eval_in_ci/digest.md" in _step(TEMPLATE, "Post sticky PR comment")["with"]["script"]


@pytest.mark.parametrize("path", [TEMPLATE, SELFTEST], ids=["template", "selftest"])
def test_sticky_comment_runs_on_dispatch_and_finds_the_pr(path: Path) -> None:
    if not path.is_file():
        pytest.skip("selftest not next to this guide")
    step = _step(path, "Post sticky PR comment")
    assert "github.event_name == 'pull_request'" in step["if"]
    assert "github.event_name == 'workflow_dispatch'" in step["if"]
    script = step["with"]["script"]
    assert "github.rest.pulls.list" in script
    assert "state: 'open'" in script
    assert "head: `${owner}:${context.ref.replace('refs/heads/', '')}`" in script
    assert "prs[0].number" in script


def _run_sh_args(tmp_path: Path, *args: str) -> list[str]:
    stub = tmp_path / "uv"
    stub.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env.update(OPIK_API_KEY="k", OPIK_WORKSPACE="w")
    out = subprocess.run(
        ["bash", str(RUN_SH), *args], cwd=ROOT, env=env, capture_output=True, text=True, check=True
    ).stdout
    # WHY: the stub prints one arg per line for each uv call; the last call is the eval.
    calls = out.split("run\npython\nrun_eval.py\n")
    return calls[-1].splitlines()


def test_run_sh_drops_only_an_empty_first_arg(tmp_path: Path) -> None:
    assert _run_sh_args(tmp_path, "", "--out", "d.md")[-2:] == ["--out", "d.md"]
    assert _run_sh_args(tmp_path, "--out", "d.md", "")[-3:] == ["--out", "d.md", ""]
    assert _run_sh_args(tmp_path, "--mark-baseline")[-1] == "--mark-baseline"


def test_optimize_is_dispatch_only() -> None:
    assert set(_on(_load(OPTIMIZE))) == {"workflow_dispatch"}


def test_optimize_inputs_reach_shell_through_env() -> None:
    for line in OPTIMIZE.read_text(encoding="utf-8").splitlines():
        if "${{ inputs." in line:
            assert re.match(r"^\s*[A-Z_]+: \$\{\{ inputs\.", line), line


def test_optimize_permissions() -> None:
    perms = _load(OPTIMIZE)["permissions"]
    assert perms == {"contents": "write", "pull-requests": "write", "actions": "write"}


def test_optimize_commits_only_the_prompt_and_tolerates_no_op() -> None:
    run = _step(OPTIMIZE, "Open a draft PR for the gate")["run"]
    adds = [line.strip() for line in run.splitlines() if line.strip().startswith("git add")]
    assert adds == ["git add examples/eval_in_ci/prompts/system.txt"]
    assert run.index("git diff --cached --quiet") < run.index("git commit")
    assert '--base "$GITHUB_REF_NAME"' in run
    assert "gh workflow run opik-eval.yml" in run
