"""Pure helpers around the verdict: schema, parsing, detection summary."""

from __future__ import annotations

from collections import defaultdict

from roadwork_demo.data import VERDICTS

# Feedback score names, shared by metrics, scripts and the gate.
VERDICT_ACCURACY = "verdict_accuracy"
JUDGE_VERDICT_CORRECT = "judge_verdict_correct"
ONLINE_VERDICT_CORRECT = "online_verdict_correct"
HUMAN_VERDICT = "human_verdict"
# Category values of the human_verdict feedback definition in Opik.
HUMAN_VERDICT_CATEGORIES = {"clear": 0.0, "partial": 1.0, "blocked": 2.0}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def parse_verdict(tool_input: dict | None, raw_text: str = "") -> dict:
    """Validate the model's structured answer. Never raises; bad output -> 'invalid'."""
    if isinstance(tool_input, dict) and tool_input.get("verdict") in VERDICTS:
        return {"verdict": tool_input["verdict"], "reason": str(tool_input.get("reason") or "")}
    reason = raw_text.strip() or (str(tool_input) if tool_input else "model returned no verdict")
    return {"verdict": "invalid", "reason": reason}


def format_detections(detections: list[dict]) -> str:
    """One line per class: count and highest confidence."""
    if not detections:
        return "no objects detected"
    by_label = defaultdict(list)
    for d in detections:
        by_label[d["label"]].append(d["confidence"])
    lines = [
        f"{label} x{len(confs)} (max confidence {max(confs):.2f})"
        for label, confs in sorted(by_label.items(), key=lambda kv: -len(kv[1]))
    ]
    return "\n".join(lines)


def extract_verdict(trace_output: dict | None) -> str | None:
    """Verdict from a trace's output, whether the pipeline ran directly or under evaluate()."""
    if not isinstance(trace_output, dict):
        return None
    inner = trace_output.get("output")
    if isinstance(inner, dict):
        trace_output = inner
    verdict = trace_output.get("verdict")
    return verdict if isinstance(verdict, str) else None
