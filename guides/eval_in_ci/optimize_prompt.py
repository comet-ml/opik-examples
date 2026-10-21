"""Quick win: let Opik's MetaPromptOptimizer improve the scenario prompt."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import opik
from opik.evaluation.metrics import score_result

from example_task import DATASET_NAME, build_metric

DEFAULT_MODEL = os.environ.get("OPIK_EXAMPLES_MODEL", "openai/gpt-4o-mini")
DEFAULT_MAX_TRIALS = 5
SUB_METRICS = ("actors_correct", "maneuver_correct", "parameters_correct")
_INVALID_JSON = "invalid json"
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?(?P<body>.*?)\s*```$", re.DOTALL)

DEFAULT_SYSTEM_PROMPT = (
    "You turn a short description of a driving scenario into a structured plan. "
    "Answer with a single JSON object with exactly these keys and nothing else: "
    '"actors" (list of strings), "maneuver" (string), and "parameters" '
    '(object with integer "speed_mps" and integer "gap_m"). '
    'Actors always start with "ego". Name every other actor with one '
    "snake_case noun and drop modifiers (for example a slow truck is truck). "
    "Maneuver is one short snake_case name such as follow, lane_change_left, "
    "brake, overtake or merge. Use only integers in meters per second and meters."
)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    return match.group("body") if match else stripped


def _invalid_json_scores() -> list[score_result.ScoreResult]:
    scores = [score_result.ScoreResult(name=name, value=0.0, reason=_INVALID_JSON) for name in SUB_METRICS]
    scores.append(
        score_result.ScoreResult(name="scenario_pass", value=0.0, reason=f"failed: {_INVALID_JSON}")
    )
    scores.append(score_result.ScoreResult(name="n_metrics_failed", value=float(len(SUB_METRICS))))
    return scores


def composite_metric_adapter(dataset_item: dict[str, Any], llm_output: str) -> list[score_result.ScoreResult]:
    """Score raw LLM text with the composite metric. Optimizer metric function."""
    try:
        parsed = json.loads(_strip_fences(llm_output))
    except (ValueError, TypeError):
        return _invalid_json_scores()
    if not isinstance(parsed, dict):
        return _invalid_json_scores()
    return build_metric().score(expected=dataset_item["expected"], output=parsed)


# WHY: the optimizer requires a __name__ and reads this entry as the objective.
composite_metric_adapter.__name__ = "scenario_pass"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dataset", default=DATASET_NAME, help="Opik dataset name")
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="LiteLLM model name (default: $OPIK_EXAMPLES_MODEL, else openai/gpt-4o-mini)",
    )
    p.add_argument("--max-trials", type=int, default=DEFAULT_MAX_TRIALS)
    p.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help="File with the starting system prompt (default: built-in prompt)",
    )
    return p


def _print_prompt(prompt: Any) -> None:
    from opik_optimizer import ChatPrompt

    if isinstance(prompt, ChatPrompt):
        if prompt.system is not None:
            print(prompt.system)
        else:
            for message in prompt.get_messages():
                print(f"[{message['role']}] {message['content']}")
    elif isinstance(prompt, dict):
        for key, value in prompt.items():
            print(f"[{key}]")
            print(getattr(value, "system", value))
    else:
        print(prompt)


# WHY: toy ceiling - only about 5 of 12 scenarios are inferable from their input, so max score is 5/12.
def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        from opik_optimizer import ChatPrompt, MetaPromptOptimizer

        system = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else DEFAULT_SYSTEM_PROMPT
        prompt = ChatPrompt(name="scenario-generator", system=system, user="{input}", model=args.model)
        client = opik.Opik()
        dataset = client.get_dataset(args.dataset)
        optimizer = MetaPromptOptimizer(model=args.model, n_threads=2, verbose=1)
        result = optimizer.optimize_prompt(
            prompt=prompt,
            dataset=dataset,
            metric=composite_metric_adapter,
            max_trials=args.max_trials,
        )
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"initial score: {result.initial_score}")
    print(f"best score: {result.score}")
    print("best prompt:")
    _print_prompt(result.prompt)
    try:
        print(f"run link: {result.get_run_link()}")
    except Exception:
        print("run link unavailable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
