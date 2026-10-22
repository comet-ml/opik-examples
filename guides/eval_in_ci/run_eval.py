"""Run an Opik evaluation and render a release digest, or digest an existing run."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opik import evaluate

import eval_compare
import example_task
import opik_access
from opik_access import ConfigError

DRY_RUN: bool = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))
DRY_RUN_HINT = (
    "Hint: no OPIK_API_KEY / OPIK_WORKSPACE in the environment. "
    'Set them, run "opik configure", or use "demo" for an offline run.'
)
DEFAULT_METRIC = "example_task:build_metric"
PROJECT_HELP = (
    "Project hint for experiment lookup by name. Opik files experiments under "
    "the dataset's project; this value is tried first, then ignored."
)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_eval", description="Opik evaluation in CI: run and digest.")
    sub = parser.add_subparsers(dest="mode", required=True)

    run = sub.add_parser("run", help="Evaluate a task and compare to the baseline")
    run.add_argument("--dataset", required=True, help="Opik dataset name")
    run.add_argument("--project", help=PROJECT_HELP)
    run.add_argument("--task", required=True, help="Task as module:callable")
    run.add_argument(
        "--metric",
        default=DEFAULT_METRIC,
        help="Zero-arg callable returning the metric (default: %(default)s)",
    )
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
    _add_common(dig)

    demo = sub.add_parser(
        "demo", help="Offline demo: compare the toy agent v1 vs v2 in-process, no credentials needed."
    )
    demo.add_argument("--pass-threshold", type=int, default=None, help="Trials that must pass per item")
    demo.add_argument("--policy", type=Path, help="Path to opik-release-policy.yaml")
    demo.add_argument("--out", type=Path, help="Write the markdown digest here")
    demo.add_argument("--json", type=Path, help="Write the JSON digest here")
    return parser


def _fmt_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


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
    mark_baseline: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Fetch rows, classify, apply policy, and render markdown plus JSON."""
    ids = [candidate_id] if baseline_id is None else [baseline_id, candidate_id]
    rows = opik_access.fetch_compare_rows(client, dataset_id, ids)
    runs = eval_compare.rows_to_item_runs(rows)
    cmp = eval_compare.classify(
        runs,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        pass_threshold=pass_threshold,
    )
    policy, policy_source = eval_compare.load_policy(policy_path)
    verdict = eval_compare.evaluate_policy(cmp, policy, mark_baseline=mark_baseline)

    ui_base, workspace = opik_access.ui_base_and_workspace(client)
    # WHY: trace ids in the digest are the candidate's, so the project must be too.
    project_id: str | None = None
    for row in rows:
        for item in getattr(row, "experiment_items", None) or []:
            if getattr(item, "experiment_id", None) == candidate_id:
                project_id = getattr(item, "project_id", None)
            if project_id:
                break
        if project_id:
            break
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
    return (
        eval_compare.render_markdown(cmp, verdict, meta),
        eval_compare.render_json(cmp, verdict, meta),
    )


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
    print(
        "Demo mode: no Opik connection; comparing AGENT_VERSION=v1 (baseline) with v2 (candidate) in-process."
    )
    runs: list[eval_compare.ItemRun] = []
    metric = example_task.build_metric(track=False)
    for version in ("v1", "v2"):
        for item in example_task.SCENARIOS:
            output = example_task.scenario_agent(item["scenario_id"], item["input"], version=version)
            results = metric.score(expected=item["expected"], **output)
            scores = tuple(
                eval_compare.RunScore(name=r.name, value=r.value, reason=r.reason) for r in results
            )
            runs.append(
                eval_compare.ItemRun(
                    experiment_id=f"local-{version}",
                    dataset_item_id=item["scenario_id"],
                    trace_id=None,
                    label=item["scenario_id"],
                    scores=scores,
                )
            )
    cmp = eval_compare.classify(
        runs, baseline_id="local-v1", candidate_id="local-v2", pass_threshold=args.pass_threshold
    )
    policy, policy_source = eval_compare.load_policy(args.policy)
    verdict = eval_compare.evaluate_policy(cmp, policy)
    meta = eval_compare.DigestMeta(
        baseline_name="local-v1",
        candidate_name="local-v2",
        compare_url=None,
        trace_url=lambda _tid: None,
        policy_source=policy_source,
        server_version=None,
        git=_git_meta(opik_access.git_context()),
        mark_baseline=False,
    )
    # WHY: the demo is illustrative, so the exit code ignores the policy verdict.
    markdown = eval_compare.render_markdown(cmp, verdict, meta)
    _emit_files(args, markdown, eval_compare.render_json(cmp, verdict, meta))
    print('Demo exit code is always 0. In CI, use "run --fail-on-regression" so a hold fails the job.')
    return 0


def _run(args: argparse.Namespace) -> int:
    client = opik_access.make_client()
    version = opik_access.server_version(client)
    print(f"Opik server: {version}")
    task_fn = opik_access.load_callable(args.task)

    def task(item: dict[str, Any]) -> Any:
        """Call the user task with the dataset item fields as keyword args."""
        # WHY: the engine adds the item id to the dict, and it is not a dataset field.
        return task_fn(**{k: v for k, v in item.items() if k != "id"})

    metric = opik_access.load_callable(args.metric)()
    try:
        dataset = client.get_dataset(args.dataset)
    except Exception as exc:
        raise ConfigError(f"Dataset '{args.dataset}' not found or unreadable: {_fmt_error(exc)}") from exc

    ctx = opik_access.git_context(args.pr)
    name = opik_access.experiment_name(ctx)
    try:
        result = evaluate(
            dataset=dataset,
            task=task,
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
            # WHY: the baseline tag is added only after a successful run (mark_baseline).
            experiment_tags=["ci", ctx.branch] + ([] if args.mark_baseline else ["candidate"]),
            trial_count=args.trials,
            task_threads=4,
        )
    except Exception:
        print("Task or metric error during evaluation:", file=sys.stderr)
        traceback.print_exc()
        return 2
    if args.mark_baseline and not args.baseline:
        # WHY: this run becomes the baseline, so there is nothing to compare against.
        baseline_id, baseline_name = None, None
    else:
        baseline_id, baseline_name = _resolve_baseline(client, args, dataset.id, result.experiment_id)
    md, payload = _build_digest(
        client,
        dataset.id,
        baseline_id,
        baseline_name,
        result.experiment_id,
        name,
        pass_threshold=args.pass_threshold,
        policy_path=args.policy,
        git=_git_meta(ctx),
        version=version,
        mark_baseline=args.mark_baseline,
    )
    if args.mark_baseline:
        # WHY: a run with no scored items would become a baseline every later PR beats.
        if payload.get("items_scored", 0) > payload.get("items_unscored", 0):
            opik_access.mark_baseline(client, result.experiment_id)
        else:
            print("Baseline not tagged: no item carried the pass score.", file=sys.stderr)
    return _emit(args, md, payload)


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
    )
    return _emit(args, md, payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "demo":
            return _demo(args)
        return _run(args) if args.mode == "run" else _digest(args)
    except (ConfigError, eval_compare.PolicyError) as exc:
        print(str(exc), file=sys.stderr)
        if isinstance(exc, ConfigError) and DRY_RUN:
            print(DRY_RUN_HINT, file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Run failed: {_fmt_error(exc)}", file=sys.stderr)
        if os.environ.get("OPIK_EVAL_DEBUG") == "1":
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
