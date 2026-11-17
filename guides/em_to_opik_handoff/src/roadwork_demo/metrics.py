"""Opik metrics for the verdict stage."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from opik.evaluation.metrics import base_metric, score_result

from roadwork_demo.config import REPO_ROOT, get_settings
from roadwork_demo.images import encode_image
from roadwork_demo.llm import image_block, structured_json
from roadwork_demo.verdicts import JUDGE_VERDICT_CORRECT, VERDICT_ACCURACY

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["correct", "reason"],
    "additionalProperties": False,
}


class VerdictAccuracy(base_metric.BaseMetric):
    """Exact match of the pipeline verdict against the human scene label."""

    def __init__(self, name: str = VERDICT_ACCURACY):
        super().__init__(name=name, track=False)

    def score(self, verdict: str | None, expected_verdict: str, **ignored: Any) -> score_result.ScoreResult:
        got = verdict
        if got == "invalid" or got is None:
            return score_result.ScoreResult(self.name, 0.0, reason="invalid model output")
        return score_result.ScoreResult(
            self.name,
            1.0 if got == expected_verdict else 0.0,
            reason=f"predicted {got}, expected {expected_verdict}",
        )


def judge_result_to_score(tool_input: dict | None) -> tuple[float, str]:
    """Turn the judge's structured answer into (value, reason). Missing decision -> 0."""
    if not isinstance(tool_input, dict) or not isinstance(tool_input.get("correct"), bool):
        return 0.0, "judge returned no decision"
    return (1.0 if tool_input["correct"] else 0.0), str(tool_input.get("reason") or "")


@lru_cache(maxsize=1)
def judge_prompt() -> str:
    return (REPO_ROOT / "prompts" / "judge.txt").read_text().strip()


def judge_verdict(image_b64: str, verdict: str, reason: str) -> tuple[float, str]:
    """Ask the judge model (sees the image, not the ground truth) if the verdict is right."""
    content = [
        image_block(image_b64),
        {"type": "text", "text": f"System verdict: {verdict}\nSystem reason: {reason}"},
    ]
    parsed, _ = structured_json(
        get_settings().judge_model, judge_prompt(), content, JUDGE_SCHEMA, max_tokens=4000
    )
    return judge_result_to_score(parsed)


class JudgeVerdictCorrect(base_metric.BaseMetric):
    """LLM judge: is the verdict right for this image? Does not see the ground truth."""

    def __init__(self, image_paths: dict[str, str], name: str = JUDGE_VERDICT_CORRECT):
        super().__init__(name=name, track=False)
        # WHY: images are read from local disk by file name. Large base64 fields in Opik
        # dataset items come back as attachment references, not image bytes.
        self._image_paths = image_paths

    def score(
        self, verdict: str | None, file_name: str, reason: str = "", **ignored: Any
    ) -> score_result.ScoreResult:
        if verdict in (None, "invalid"):
            return score_result.ScoreResult(self.name, 0.0, reason="invalid model output")
        path = self._image_paths.get(file_name)
        if path is None or not Path(path).exists():
            return score_result.ScoreResult(
                self.name, 0.0, reason=f"image not found locally: {file_name}", scoring_failed=True
            )
        value, judge_reason = judge_verdict(encode_image(Path(path)), verdict, reason)
        return score_result.ScoreResult(self.name, value, reason=judge_reason)


def accuracy_by_class(test_results: list) -> dict[str, float]:
    """Mean verdict accuracy per expected verdict, over the items that were scored."""
    per_class = defaultdict(list)
    for tr in test_results:
        expected = tr.test_case.dataset_item_content.get("expected_verdict")
        for sr in tr.score_results:
            if sr.name == VERDICT_ACCURACY and not sr.scoring_failed:
                per_class[expected].append(sr.value)
    return {cls: sum(values) / len(values) for cls, values in per_class.items()}


def per_class_accuracy(test_results: list) -> list[score_result.ScoreResult]:
    """Experiment-level scores accuracy_<class>, for evaluate(experiment_scoring_functions=[...])."""
    return [
        score_result.ScoreResult(name=f"accuracy_{cls}", value=value)
        for cls, value in sorted(accuracy_by_class(test_results).items())
    ]
