"""Optimize step: improve the system prompt file so a pull request can put it through the gate."""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opik.evaluation.metrics import score_result

import ci_output
import config
import opik_access
from composite_metric import DEFAULT_PASS_NAME
from opik_access import ConfigError
from scenarios import build_metric, parse_plan

DEFAULT_MAX_TRIALS = 3
DEFAULT_PROMPT_FILE = Path("prompts/system.txt")
TITLE = "Optimize prompt"


@functools.cache
def _metric() -> Any:
    """Build the composite metric once; the optimizer scores every item of every trial."""
    return build_metric(track=False)


# WHY: the composite metric is the objective because "better prompt" means "more scenarios pass
# every threshold", the same number the PR gate compares.
def composite_metric_adapter(dataset_item: dict[str, Any], llm_output: str) -> list[score_result.ScoreResult]:
    """Score raw LLM text with the composite metric. Optimizer metric function."""
    return _metric().score(expected=dataset_item["expected"], output=parse_plan(llm_output))


# WHY: the optimizer requires a __name__ and reads this entry as the objective.
composite_metric_adapter.__name__ = DEFAULT_PASS_NAME


def run_optimizer(system_text: str, dataset: Any, *, max_trials: int) -> Any:
    """Run MetaPromptOptimizer from the given system prompt; this creates the Optimization run."""
    # WHY: imported here so the evaluate step and the tests need no optimizer install.
    try:
        from opik_optimizer import ChatPrompt, MetaPromptOptimizer
    except ModuleNotFoundError as exc:
        raise ConfigError(f"{exc}; run: uv sync --extra optimizer") from exc

    prompt = ChatPrompt(name=config.PROMPT_NAME, system=system_text, user="{input}", model=config.GEN_MODEL)
    optimizer = MetaPromptOptimizer(model=config.GEN_MODEL, n_threads=4, verbose=1)
    return optimizer.optimize_prompt(
        prompt=prompt, dataset=dataset, metric=composite_metric_adapter, max_trials=max_trials
    )


def best_system_text(result: Any) -> str:
    """The optimized system prompt, or ConfigError when the result is not one system prompt."""
    prompt = result.prompt
    if isinstance(prompt, dict):
        raise ConfigError("The optimizer returned several prompts; expected one.")
    # WHY: get_messages() covers both shapes: candidates built from messages leave .system None.
    system = next(
        (
            m["content"]
            for m in prompt.get_messages()
            if m.get("role") == "system" and isinstance(m.get("content"), str)
        ),
        None,
    )
    if not system:
        raise ConfigError("The optimizer did not return a single prompt with a system message.")
    return system.strip()


def starting_prompt(client: Any, name: str, prompt_file: Path) -> str:
    """The production version's text, else the prompt file's; ConfigError when both are empty."""
    production = opik_access.get_production_prompt(client, name)
    text = (production.prompt or "").strip() if production is not None else ""
    if not text and prompt_file.is_file():
        text = prompt_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ConfigError(f"No production version of {name} and no text in {prompt_file}.")
    return text


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="optimize_prompt", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--prompt-file", type=Path, default=DEFAULT_PROMPT_FILE, help="System prompt file to improve"
    )
    parser.add_argument("--prompt-name", default=config.PROMPT_NAME, help="Prompt library name")
    parser.add_argument("--max-trials", type=int, default=DEFAULT_MAX_TRIALS, help="Optimizer trials")
    parser.add_argument(
        "--summary", type=Path, help="Append the markdown summary here ($GITHUB_STEP_SUMMARY)"
    )
    parser.add_argument("--github-output", type=Path, help="Append step outputs here ($GITHUB_OUTPUT)")
    parser.add_argument("--json", type=Path, help="Write the JSON summary here")
    return parser


def _dry_run(args: argparse.Namespace) -> int:
    print(f"[DRY RUN] would start from the production version of {args.prompt_name}, else {args.prompt_file}")
    print(
        f"[DRY RUN] would run MetaPromptOptimizer ({config.GEN_MODEL}, {args.max_trials} trials) "
        f"on {config.DATASET_NAME}"
    )
    print(f"[DRY RUN] would write the best prompt to {args.prompt_file} when it changed")
    print("Set OPIK_API_KEY and OPIK_WORKSPACE (and a model provider key) to run it for real.")
    ci_output.write_github_output(args.github_output, {"changed": "false"})
    return 0


def _run(args: argparse.Namespace) -> int:
    client = opik_access.make_client()
    try:
        dataset = client.get_dataset(config.DATASET_NAME)
    except Exception as exc:
        raise ConfigError(
            f"Dataset '{config.DATASET_NAME}' not found or unreadable: {type(exc).__name__}: {exc}"
        ) from exc
    start = starting_prompt(client, args.prompt_name, args.prompt_file)
    result = run_optimizer(start, dataset, max_trials=args.max_trials)
    best = best_system_text(result)
    changed = best != start.strip()
    if changed:
        args.prompt_file.write_text(best + "\n", encoding="utf-8")

    try:
        run_link = result.get_run_link() or ""
    except Exception:
        run_link = ""
    initial, best_score = _fmt(result.initial_score), _fmt(result.score)
    optimizer_line = f"Optimizer: initial {initial} -> best {best_score}"
    if run_link:
        optimizer_line += f" ([run]({run_link}))"
    markdown = "\n".join(
        [f"## {TITLE}", "", optimizer_line, f"Prompt file: {'changed' if changed else 'unchanged'}"]
    )
    print(markdown)
    ci_output.append_text(args.summary, markdown)
    ci_output.write_github_output(
        args.github_output,
        {
            "changed": "true" if changed else "false",
            "initial_score": initial,
            "best_score": best_score,
            "run_link": run_link,
        },
    )
    ci_output.write_json(
        args.json,
        {"changed": changed, "initial_score": initial, "best_score": best_score, "run_link": run_link},
    )
    return 0


def _step(args: argparse.Namespace) -> int:
    if config.DRY_RUN:
        return _dry_run(args)
    return _run(args)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return ci_output.run_step(
        lambda: _step(args),
        title=TITLE,
        summary=args.summary,
        outcome=lambda: f"The prompt file {args.prompt_file} was not changed.",
    )


if __name__ == "__main__":
    sys.exit(main())
