"""Promotion gate for the retrain loop: a candidate must beat the current model offline.

Usage: uv run python -m roadwork_demo.gate <candidate_experiment> <current_experiment>
Compares mean verdict_accuracy of two Opik experiments run on the same dataset.
"""

from __future__ import annotations

import sys
from typing import Literal

from roadwork_demo.verdicts import VERDICT_ACCURACY


def decide(candidate: float, current: float, min_delta: float = 0.0) -> Literal["promote", "hold"]:
    return "promote" if candidate > current + min_delta else "hold"


def latest(experiments: list, name: str):
    """Most recent experiment named exactly `name`, or None.

    Opik's lookup by name also returns experiments that merely contain the name, and a re-run
    creates a second experiment with the same name. Ids are time-ordered (UUID v7).
    """
    exact = [e for e in experiments if e.name == name]
    return max(exact, key=lambda e: e.id) if exact else None


def mean_score(experiment_name: str, score_name: str = VERDICT_ACCURACY) -> float:
    import opik
    from opik.exceptions import ExperimentNotFound

    from roadwork_demo.config import get_settings

    get_settings()  # loads .env so Opik uses this demo's workspace and project
    client = opik.Opik()

    try:
        experiment = latest(client.get_experiments_by_name(experiment_name), experiment_name)
    except ExperimentNotFound:
        experiment = None
    if experiment is None:
        raise SystemExit(f"Opik experiment not found: {experiment_name}")
    values = []
    for item in experiment.get_items():
        for score in item.feedback_scores or []:
            if score["name"] == score_name:
                values.append(float(score["value"]))
    if not values:
        raise SystemExit(f"No '{score_name}' scores on experiment {experiment_name}")
    return sum(values) / len(values)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    candidate, current = (mean_score(name) for name in sys.argv[1:3])
    decision = decide(candidate, current)
    print(f"candidate {sys.argv[1]}: {candidate:.3f}")
    print(f"current   {sys.argv[2]}: {current:.3f}")
    print(f"decision: {decision}")


if __name__ == "__main__":
    main()
