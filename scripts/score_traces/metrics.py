"""Metrics + eval definitions — single source of truth for offline evaluation.

Contains a minimal user-defined Opik metric (no LLM) for the Python-metric example
(the SDK's own metric interface: subclass BaseMetric and implement score()), plus
the EVALS list: the judges & metrics to run (copy a block to add one).

The score `name` and `variables` mapping here are identical to what an online
evaluation rule needs, so migrating later is a drop-in (see README, Stage 1).
"""

from dataclasses import dataclass
from typing import Any

from opik.evaluation.metrics import GEval, Hallucination, base_metric, score_result
from opik.evaluation.metrics.base_metric import BaseMetric

from model import build_judge_model


class ExactMatch(base_metric.BaseMetric):
    """Scores 1.0 when output exactly equals reference, else 0.0."""

    def __init__(self, name: str = "exact_match"):
        super().__init__(name=name, track=False)

    def score(self, output: str, reference: str, **ignored: Any) -> score_result.ScoreResult:
        hit = output == reference
        return score_result.ScoreResult(
            value=1.0 if hit else 0.0,
            name=self.name,
            reason="exact match" if hit else f"output {output!r} != reference {reference!r}",
        )


judge_model = build_judge_model()


@dataclass
class Eval:
    """One evaluation: its score name, the live SDK metric, and the variable mapping.

    `variables` maps each metric score() parameter to a dotted trace field-path
    (the Opik UI "variable mapping"). `name` is the feedback-score name.
    """

    name: str
    metric: BaseMetric
    variables: dict[str, str]


# ============================================================
# 2. EVALS — your judges & metrics (copy a block to add one)
# ============================================================
EVALS: list[Eval] = [
    # Built-in preset judge (lead example).
    Eval(
        name="hallucination",
        metric=Hallucination(model=judge_model, name="hallucination"),
        variables={
            "input": "input.question",
            "output": "output.answer",
            "context": "output.context",
        },
    ),
    # G-Eval custom judge (author criteria as text).
    Eval(
        name="relevance",
        metric=GEval(
            model=judge_model,
            name="relevance",
            task_introduction=("You judge whether an answer (OUTPUT) is relevant to the question (INPUT)."),
            evaluation_criteria=(
                "Return 1 if the OUTPUT directly addresses the INPUT question, 0 if it is "
                "off-topic or evasive."
            ),
        ),
        variables={"input": "input.question", "output": "output.answer"},
    ),
    # User-defined Python metric (no LLM).
    Eval(
        name="exact_match",
        metric=ExactMatch(name="exact_match"),
        variables={"output": "output.answer", "reference": "input.expected"},
    ),
]
