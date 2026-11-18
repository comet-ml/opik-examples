"""Agreement between human reviewers, the pipeline and the LLM judge on reviewed traces.

Usage: uv run python scripts/07_agreement.py
Reads human_verdict annotations from the review queue and reports:
  1. human vs model verdict (3 classes): percent agreement and Cohen's kappa
  2. judge vs human on "is the model's verdict correct" (0/1): percent agreement
Also writes human_says_correct back onto each trace so both columns sit side by side in Opik.
"""

from __future__ import annotations

import opik

from roadwork_demo.agreement import cohens_kappa, percent_agreement
from roadwork_demo.config import exit_if_dry_run, get_settings
from roadwork_demo.review import find_review_queue
from roadwork_demo.verdicts import HUMAN_VERDICT as HUMAN
from roadwork_demo.verdicts import (
    HUMAN_VERDICT_CATEGORIES,
    JUDGE_VERDICT_CORRECT,
    ONLINE_VERDICT_CORRECT,
    extract_verdict,
)

JUDGE_SCORES = (JUDGE_VERDICT_CORRECT, ONLINE_VERDICT_CORRECT)
LABEL_BY_VALUE = {value: label for label, value in HUMAN_VERDICT_CATEGORIES.items()}


def human_label(score) -> str | None:
    return score.category_name or LABEL_BY_VALUE.get(float(score.value))


def main() -> None:
    s = get_settings()
    exit_if_dry_run(s, f"compare human, model and judge verdicts in the queue '{s.queue_name}'")
    client = opik.Opik()
    queue = find_review_queue(client, s)
    if queue is None:
        raise SystemExit(f"Queue '{s.queue_name}' not found. Run scripts/06_review_queue.py first.")

    rows = []
    for item in queue.get_items():
        trace = client.get_trace_content(item.id)
        scores = {sc.name: sc for sc in (trace.feedback_scores or [])}
        if HUMAN not in scores:
            continue
        rows.append(
            {
                "id": trace.id,
                "human": human_label(scores[HUMAN]),
                "model": extract_verdict(trace.output),
                "judges": {n: int(float(scores[n].value) >= 0.5) for n in JUDGE_SCORES if n in scores},
            }
        )

    if not rows:
        print(
            f"No '{HUMAN}' annotations yet in queue '{s.queue_name}'. "
            "Annotate some traces in the Opik UI, then re-run."
        )
        return

    humans, models = [r["human"] for r in rows], [r["model"] for r in rows]
    print(f"Reviewed traces: {len(rows)}")
    print("\n1. Human vs model verdict")
    print(f"   percent agreement: {percent_agreement(humans, models):.1%}")
    print(f"   Cohen's kappa:     {cohens_kappa(humans, models):.2f}")

    # WHY: one figure per judge. The offline judge and the online rule use different models.
    print("\n2. Judge vs human on 'model verdict is correct'")
    for name in JUDGE_SCORES:
        judged = [r for r in rows if name in r["judges"]]
        if not judged:
            print(f"   {name}: no scores on the reviewed traces")
            continue
        human_correct = [int(r["human"] == r["model"]) for r in judged]
        judge_correct = [r["judges"][name] for r in judged]
        print(
            f"   {name}: {percent_agreement(judge_correct, human_correct):.1%} "
            f"agreement on {len(judged)} traces"
        )

    disagreements = [r for r in rows if r["human"] != r["model"]]
    print(f"\nHuman / model disagreements: {len(disagreements)} (candidates for the next dataset version)")
    for r in disagreements:
        print(f"   {r['id']}  human={r['human']}  model={r['model']}  judges={r['judges']}")

    client.log_traces_feedback_scores(
        [
            {
                "id": r["id"],
                "name": "human_says_correct",
                "value": float(r["human"] == r["model"]),
                "reason": f"human={r['human']}, model={r['model']}",
            }
            for r in rows
        ]
    )
    client.flush()
    print("\nLogged human_says_correct onto the reviewed traces.")


if __name__ == "__main__":
    main()
