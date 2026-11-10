"""Run an Opik evaluation and render a release digest, or digest an existing run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from opik import evaluate, run_tests

import ci_output
import config
import eval_compare
import opik_access
from opik_access import ConfigError

DRY_RUN: bool = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))
DRY_RUN_HINT = (
    "Hint: no OPIK_API_KEY / OPIK_WORKSPACE in the environment. "
    'Set them, run "opik configure", or use "demo" for an offline run.'
)
NOTHING_DONE = "Nothing was tagged or promoted."
PROJECT_HELP = (
    "Project hint for experiment lookup by name. Opik files experiments under "
    "the dataset's project; this value is tried first, then ignored."
)


class TaskError(RuntimeError):
    """Raised when the user's task or metric crashes during the evaluation."""


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--baseline", help="Baseline experiment name or id")
    p.add_argument(
        "--pass-threshold",
        type=int,
        default=None,
        help="Trials that must pass for an item to count as passing",
    )
    p.add_argument("--policy", type=Path, help="Path to opik-release-policy.yaml")
    p.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit 1 when the policy verdict is hold or insufficient_evidence",
    )
    p.add_argument("--out", type=Path, help="Write the markdown digest here")
    p.add_argument("--json", type=Path, help="Write the JSON digest here")
    p.add_argument("--summary", type=Path, help="Append a failure note here (e.g. $GITHUB_STEP_SUMMARY)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_eval", description="Opik evaluation in CI: run and digest.")
    sub = parser.add_subparsers(dest="mode", required=True)

    run = sub.add_parser("run", help="Evaluate a task and compare to the baseline")
    run.add_argument("--dataset", required=True, help="Opik dataset name")
    run.add_argument("--project", help=PROJECT_HELP)
    run.add_argument("--task", required=True, help="Task as module:callable")
    run.add_argument(
        "--metric", required=True, help="Zero-arg callable returning the metric, as module:callable"
    )
    run.add_argument("--prompt-file", type=Path, help="Prompt file to register as the candidate prompt")
    run.add_argument("--prompt-name", default=config.PROMPT_NAME, help="Prompt name (default: %(default)s)")
    run.add_argument("--setup", help="Optional module:callable run once before the evaluation")
    run.add_argument("--suite-task", help="Optional module:callable task for the test suite")
    run.add_argument("--traffic", help="Optional module:callable that generates simulated traffic")
    run.add_argument("--suite-name", help="Test suite name (pairs with --suite-task)")
    run.add_argument("--label-key", default="scenario_id", help="Dataset field used to label items")
    run.add_argument("--trials", type=int, default=1, help="Trials per item")
    run.add_argument(
        "--mark-baseline",
        action="store_true",
        help="Tag this experiment as the baseline",
    )
    run.add_argument("--pr", help="Pull request number (default: from CI env)")
    _add_common(run)

    dig = sub.add_parser("digest", help="Digest an existing experiment")
    dig.add_argument("--experiment", required=True, help="Experiment name or id")
    dig.add_argument("--project", help=PROJECT_HELP)
    dig.add_argument("--label-key", default="scenario_id", help="Dataset field used to label items")
    _add_common(dig)

    demo = sub.add_parser(
        "demo",
        help="Offline demo: score sample outputs of the weak and system prompts, no credentials needed.",
    )
    demo.add_argument("--pass-threshold", type=int, default=None, help="Trials that must pass per item")
    demo.add_argument("--policy", type=Path, help="Path to opik-release-policy.yaml")
    demo.add_argument("--out", type=Path, help="Write the markdown digest here")
    demo.add_argument("--json", type=Path, help="Write the JSON digest here")
    return parser


def _fmt_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class _Compared:
    cmp: eval_compare.Comparison
    verdict: eval_compare.PolicyVerdict
    meta: eval_compare.DigestMeta
    project_id: str | None
    ui_base: str
    workspace: str


def _compare(
    client: Any,
    dataset_id: str,
    baseline_id: str | None,
    baseline_name: str | None,
    candidate_id: str,
    candidate_name: str,
    *,
    pass_threshold: int | None,
    policy: eval_compare.Policy,
    policy_source: str,
    git: dict[str, str],
    version: str | None,
    label_key: str = "scenario_id",
    mark_baseline: bool = False,
    suite: eval_compare.SuiteResult | None = None,
) -> _Compared:
    """Fetch rows, classify and apply the policy."""
    ids = [candidate_id] if baseline_id is None else [baseline_id, candidate_id]
    rows = opik_access.fetch_compare_rows(client, dataset_id, ids)
    runs = eval_compare.rows_to_item_runs(rows, label_key=label_key)
    cmp = eval_compare.classify(
        runs,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        pass_threshold=pass_threshold,
    )
    verdict = eval_compare.evaluate_policy(cmp, policy, mark_baseline=mark_baseline, suite=suite)

    ui_base, workspace = opik_access.ui_base_and_workspace(client)
    # WHY: trace ids in the digest are the candidate's, so the project must be too.
    project_id = next(
        (
            item.project_id
            for row in rows
            for item in row.experiment_items or []
            if item.experiment_id == candidate_id and item.project_id
        ),
        None,
    )
    meta = eval_compare.DigestMeta(
        baseline_name=baseline_name,
        candidate_name=candidate_name,
        compare_url=eval_compare.compare_url(ui_base, workspace, dataset_id, ids),
        trace_url=opik_access.trace_url_builder(ui_base, workspace, project_id),
        policy_source=policy_source,
        server_version=version,
        git=git,
        mark_baseline=mark_baseline,
    )
    return _Compared(cmp, verdict, meta, project_id, ui_base, workspace)


def _render(
    cmp: eval_compare.Comparison, verdict: eval_compare.PolicyVerdict, meta: eval_compare.DigestMeta
) -> tuple[str, dict[str, Any]]:
    return eval_compare.render_markdown(cmp, verdict, meta), eval_compare.render_json(cmp, verdict, meta)


def _build_digest(
    client: Any,
    dataset_id: str,
    baseline_id: str | None,
    baseline_name: str | None,
    candidate_id: str,
    candidate_name: str,
    *,
    pass_threshold: int | None,
    policy_path: Path | None,
    git: dict[str, str],
    version: str | None,
    label_key: str = "scenario_id",
) -> tuple[str, dict[str, Any]]:
    """Fetch rows, classify, apply policy, and render markdown plus JSON."""
    policy, policy_source = eval_compare.load_policy(policy_path)
    c = _compare(
        client,
        dataset_id,
        baseline_id,
        baseline_name,
        candidate_id,
        candidate_name,
        pass_threshold=pass_threshold,
        policy=policy,
        policy_source=policy_source,
        git=git,
        version=version,
        label_key=label_key,
    )
    return _render(c.cmp, c.verdict, c.meta)


def _emit_files(args: argparse.Namespace, markdown: str, payload: dict[str, Any]) -> None:
    """Print the markdown digest and write the optional --out and --json files."""
    print(markdown)
    if args.out:
        args.out.write_text(markdown + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _emit(args: argparse.Namespace, markdown: str, payload: dict[str, Any]) -> int:
    _emit_files(args, markdown, payload)
    if args.fail_on_regression and payload.get("status") in {
        "hold",
        "insufficient_evidence",
    }:
        return 1
    return 0


def _resolve_baseline(
    client: Any, args: argparse.Namespace, dataset_id: str, exclude_id: str
) -> tuple[str | None, str | None]:
    if args.baseline:
        exp = opik_access.resolve_experiment(client, args.baseline, getattr(args, "project", None))
        return exp.id, exp.name
    found = opik_access.find_baseline(client, dataset_id, exclude_id=exclude_id)
    return (found.id, found.name) if found else (None, None)


def _git_meta(ctx: opik_access.GitContext) -> dict[str, str]:
    meta = {"branch": ctx.branch, "sha": ctx.sha7}
    if ctx.pr_number:
        meta["pr"] = ctx.pr_number
    if ctx.actor:
        meta["actor"] = ctx.actor
    return meta


def _demo(args: argparse.Namespace) -> int:
    import scenarios

    print(
        "Demo mode: no Opik connection; scoring sample outputs of prompts/weak.txt (baseline) "
        "and prompts/system.txt (candidate) in-process."
    )
    system = (config.PROMPTS_DIR / "system.txt").read_text(encoding="utf-8")
    metric = scenarios.build_metric(track=False)
    runs: list[eval_compare.ItemRun] = []
    # WHY: sample outputs instead of model calls: the weak prompt yields no JSON, the system prompt gets
    # every item right except those whose maneuver it does not list.
    for exp_id in ("local-weak", "local-system"):
        for item in scenarios.SCENARIOS:
            expected = item["expected"]
            output: dict[str, Any] = {}
            if exp_id == "local-system":
                output = dict(expected)
                if expected["maneuver"] not in system:
                    output["maneuver"] = "brake"
            scores = tuple(
                eval_compare.RunScore(name=r.name, value=r.value, reason=r.reason)
                for r in metric.score(expected=expected, output=output)
            )
            runs.append(
                eval_compare.ItemRun(
                    experiment_id=exp_id,
                    dataset_item_id=item["scenario_id"],
                    trace_id=None,
                    label=item["scenario_id"],
                    scores=scores,
                )
            )
    cmp = eval_compare.classify(
        runs, baseline_id="local-weak", candidate_id="local-system", pass_threshold=args.pass_threshold
    )
    policy, policy_source = eval_compare.load_policy(args.policy)
    verdict = eval_compare.evaluate_policy(cmp, policy)
    meta = eval_compare.DigestMeta(
        baseline_name="local-weak",
        candidate_name="local-system",
        compare_url=None,
        trace_url=lambda _tid: None,
        policy_source=policy_source,
        server_version=None,
        git=_git_meta(opik_access.git_context()),
        mark_baseline=False,
        prompt_line="Prompt: prompts/system.txt (demo, not logged)",
    )
    # WHY: the demo is illustrative, so the exit code ignores the policy verdict.
    _emit_files(args, *_render(cmp, verdict, meta))
    print('Demo exit code is always 0. In CI, use "run --fail-on-regression" so a hold fails the job.')
    return 0


def _run(args: argparse.Namespace) -> int:
    if bool(args.suite_task) != bool(args.suite_name):
        raise ConfigError("--suite-task and --suite-name must be given together.")
    policy, policy_source = eval_compare.load_policy(args.policy)
    if policy.test_suite == "required" and not args.suite_task:
        raise eval_compare.PolicyError("Policy test_suite: required needs --suite-task and --suite-name.")
    client = opik_access.make_client()
    version = opik_access.server_version(client)
    print(f"Opik server: {version}")
    task_factory = opik_access.load_callable(args.task)
    metric = opik_access.load_callable(args.metric)()
    suite_factory = opik_access.load_callable(args.suite_task) if args.suite_task else None
    traffic = opik_access.load_callable(args.traffic) if args.traffic else None

    setup = opik_access.load_callable(args.setup)(client) if args.setup else None
    dataset = getattr(setup, "dataset", None)
    if dataset is None:
        try:
            dataset = client.get_dataset(args.dataset)
        except Exception as exc:
            raise ConfigError(f"Dataset '{args.dataset}' not found or unreadable: {_fmt_error(exc)}") from exc

    ctx = opik_access.git_context(args.pr)
    name = opik_access.experiment_name(ctx)
    text = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else None
    prompt = None
    prompt_line = "Prompt: not tracked"
    if text is not None:
        change = f"ci {ctx.sha7} {ctx.branch}" + (f" pr {ctx.pr_number}" if ctx.pr_number else "")
        prompt = opik_access.log_prompt(client, args.prompt_name, text, change_description=change)
        # WHY: read production before any promotion below, or every main run would read as unchanged.
        production = opik_access.get_production_prompt(client, args.prompt_name)
        prompt_line = f"Prompt: {prompt.name} {prompt.version}"
        if production is not None and production.version == prompt.version:
            prompt_line += " (unchanged)"
    prompts = [prompt] if prompt else None
    tags = ["ci", ctx.branch] + ([] if args.mark_baseline else ["candidate"])

    try:
        result = evaluate(
            dataset=dataset,
            task=task_factory(text),
            scoring_metrics=[metric],
            experiment_name=name,
            project_name=args.project,
            experiment_config={
                "git_sha": ctx.sha7,
                "git_branch": ctx.branch,
                "pr_number": ctx.pr_number,
                "actor": ctx.actor,
                "runner": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
                "trial_count": args.trials,
                "task_ref": args.task,
            },
            prompts=prompts,
            # WHY: the baseline tag is added only after a successful run (mark_baseline).
            experiment_tags=tags,
            trial_count=args.trials,
            task_threads=4,
        )
    except Exception as exc:
        raise TaskError(f"Task or metric error during evaluation: {_fmt_error(exc)}") from exc

    suite = None
    if suite_factory is not None:
        try:
            test_suite = client.get_test_suite(args.suite_name)
        except Exception as exc:
            raise ConfigError(
                f"Test suite '{args.suite_name}' not found or unreadable: {_fmt_error(exc)}"
            ) from exc
        try:
            suite_result = run_tests(
                test_suite,
                suite_factory(text),
                experiment_name=f"{name}-suite",
                prompts=prompts,
                experiment_tags=[*tags, "test-suite"],
            )
        except Exception as exc:
            raise TaskError(f"Task or assertion error during the test suite: {_fmt_error(exc)}") from exc
        # WHY: zero of zero would read as all items passing.
        if not suite_result.items_total:
            raise ConfigError(f"Test suite {args.suite_name} has no items")
        suite = (suite_result.items_passed, suite_result.items_total)

    baseline_id, baseline_name = _resolve_baseline(client, args, dataset.id, result.experiment_id)
    c = _compare(
        client,
        dataset.id,
        baseline_id,
        baseline_name,
        result.experiment_id,
        name,
        pass_threshold=args.pass_threshold,
        policy=policy,
        policy_source=policy_source,
        git=_git_meta(ctx),
        version=version,
        label_key=args.label_key,
        mark_baseline=args.mark_baseline,
        suite=suite,
    )
    notes = [] if suite is None else [f"Test suite: {suite[0]} of {suite[1]} passed"]
    warning = None
    if c.verdict.status == "baseline_created":
        opik_access.mark_baseline(client, result.experiment_id)
        args.done.append(f"Tagged {name} as the baseline")
        if prompt is not None:
            opik_access.assign_environment(client, prompt, config.ENV_PRODUCTION)
            notes.append(f"Promoted to production: {prompt.name} {prompt.version}")
            args.done.append(notes[-1])
        if traffic is not None:
            n = traffic(client, args.prompt_name)
            line = f"Sent {n} production requests; online rule scores them in Logs"
            project_id = getattr(setup, "project_id", None) or c.project_id
            if project_id:
                line += f": {opik_access.logs_url(c.ui_base, c.workspace, project_id)}"
            notes.append(line)
        failed = [cr.name for cr in c.verdict.criteria if not cr.passed]
        if failed:
            warning = "Warning: promoted with failed criteria: " + ", ".join(failed)
    elif args.mark_baseline:
        # WHY: a run with no scored items would become a baseline every later PR beats.
        print("Baseline not tagged: no item carried the pass score.", file=sys.stderr)
    meta = replace(c.meta, prompt_line=prompt_line, notes=tuple(notes), warning=warning)
    return _emit(args, *_render(c.cmp, c.verdict, meta))


def _digest(args: argparse.Namespace) -> int:
    client = opik_access.make_client()
    version = opik_access.server_version(client)
    print(f"Opik server: {version}")
    exp = opik_access.resolve_experiment(client, args.experiment, args.project)
    baseline_id, baseline_name = _resolve_baseline(client, args, exp.dataset_id, exp.id)
    md, payload = _build_digest(
        client,
        exp.dataset_id,
        baseline_id,
        baseline_name,
        exp.id,
        exp.name,
        pass_threshold=args.pass_threshold,
        policy_path=args.policy,
        git={},
        version=version,
        label_key=args.label_key,
    )
    return _emit(args, md, payload)


def _dispatch(args: argparse.Namespace) -> int:
    try:
        if args.mode == "demo":
            return _demo(args)
        return _run(args) if args.mode == "run" else _digest(args)
    except ConfigError:
        if DRY_RUN:
            print(DRY_RUN_HINT, file=sys.stderr)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # WHY: a failure after promotion (e.g. in the traffic hook) must not claim nothing changed.
    args.done = []
    return ci_output.run_step(
        lambda: _dispatch(args),
        title=f"Opik eval: {args.mode}",
        summary=getattr(args, "summary", None),
        outcome=lambda: "Done before the failure: " + "; ".join(args.done) if args.done else NOTHING_DONE,
    )


if __name__ == "__main__":
    sys.exit(main())
