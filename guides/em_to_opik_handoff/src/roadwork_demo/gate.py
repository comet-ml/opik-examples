"""Promotion gate: a candidate detector version must beat the current one on the downstream task.

Usage: python -m roadwork_demo.gate --candidate 2.0.0 [--current production] [--min-delta 0.03] [--apply]

Compares the Opik experiments detector_vlm-<candidate> and detector_vlm-<current>, item by item,
on verdict accuracy. Both must have run on the same dataset version. Without --apply it only
prints. With --apply a promote makes the candidate Production in the Comet Model Registry and the
previous Production version Staging, and the decision is written on both training experiments.
A promote is only applied over the one Production version: --apply refuses any other --current.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Any, Literal

from roadwork_demo.registry import PRODUCTION, STATUS_PRODUCTION, STATUS_STAGING
from roadwork_demo.verdicts import VERDICT_ACCURACY

Decision = Literal["promote", "hold"]
GATE_VARIANT = "detector_vlm"
# WHY: with a different verdict model or prompt, a difference in accuracy is not the detector's.
SAME_IN_BOTH = ("verdict_model", "prompts")
# WHY: floats. 0.59 - 0.56 is 0.02999..., and a gain of exactly min_delta has to promote.
EPSILON = 1e-9
# Smallest share of the dataset items that both experiments must have scored: 9 in 10.
MIN_COVERAGE = (9, 10)


class GateRefusal(ValueError):
    """The two experiments cannot be compared fairly."""


@dataclass
class Applied:
    done: bool
    lines: list[str]


@dataclass
class Paired:
    n: int
    dropped: int
    mean_candidate: float
    mean_current: float
    delta: float
    wins: int
    losses: int
    p_value: float


def sign_test_p(wins: int, losses: int) -> float:
    """Exact two-sided sign test: chance of a split at least this uneven if neither side is better."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1))
    return min(1.0, 2 * tail / 2**n)


def paired(candidate: dict[str, float], current: dict[str, float]) -> Paired:
    """Compare two experiments on the dataset items both of them scored (keys: dataset item ids)."""
    shared = sorted(candidate.keys() & current.keys())
    if not shared:
        raise ValueError("the two experiments have no dataset items in common")
    wins = sum(candidate[i] > current[i] for i in shared)
    losses = sum(candidate[i] < current[i] for i in shared)
    mean_candidate = sum(candidate[i] for i in shared) / len(shared)
    mean_current = sum(current[i] for i in shared) / len(shared)
    return Paired(
        n=len(shared),
        dropped=len(candidate.keys() ^ current.keys()),
        mean_candidate=mean_candidate,
        mean_current=mean_current,
        delta=mean_candidate - mean_current,
        wins=wins,
        losses=losses,
        p_value=sign_test_p(wins, losses),
    )


def decide(delta: float, min_delta: float = 0.03) -> Decision:
    """Promote only on a real gain of at least `min_delta`; a tie never promotes."""
    return "promote" if delta > 0 and delta >= min_delta - EPSILON else "hold"


def same_dataset_version(a: str | None, b: str | None) -> bool:
    return a is not None and a == b


def latest(experiments: list, name: str):
    """Most recent experiment named exactly `name`, or None."""
    # WHY: Opik's lookup by name also returns experiments that merely contain the name, and a
    # re-run creates a second experiment with the same name. Ids are time-ordered (UUID v7).
    exact = [e for e in experiments if e.name == name]
    return max(exact, key=lambda e: e.id) if exact else None


def find_experiment(client: Any, name: str):
    """Most recent Opik experiment named exactly `name`, or None."""
    from opik.exceptions import ExperimentNotFound

    try:
        return latest(client.get_experiments_by_name(name), name)
    except ExperimentNotFound:
        return None


def item_scores(experiment: Any, score_name: str = VERDICT_ACCURACY) -> dict[str, float]:
    """Per-item value of one feedback score, keyed by dataset item id. Unscored items are left out."""
    scores = {}
    # WHY truncate: only the scores are read; untruncated items carry the images.
    for item in experiment.get_items(truncate=True):
        for score in item.feedback_scores or []:
            if score["name"] == score_name:
                scores[item.dataset_item_id] = float(score["value"])
    return scores


def require_comparable(candidate: Any, current: Any) -> None:
    """GateRefusal unless both experiments ran on one dataset version with one model and prompt."""
    data_a, data_b = candidate.get_experiment_data(), current.get_experiment_data()
    a, b = data_a.dataset_version_id, data_b.dataset_version_id
    if not same_dataset_version(a, b):
        raise GateRefusal(
            f"{candidate.name} ran on dataset version {a} and {current.name} on {b}. "
            "Re-run both on the current dataset version before comparing them."
        )
    config_a, config_b = data_a.metadata or {}, data_b.metadata or {}
    for key in SAME_IN_BOTH:
        value_a, value_b = config_a.get(key), config_b.get(key)
        if value_a != value_b:
            both_short = isinstance(value_a, str) and isinstance(value_b, str)
            detail = f" ({value_a} against {value_b})" if both_short else ""
            raise GateRefusal(
                f"{candidate.name} and {current.name} were run with a different {key}{detail}. "
                "Re-run both with the same verdict model and prompt before comparing them."
            )


def compare(candidate: Any, current: Any, score_name: str = VERDICT_ACCURACY) -> Paired:
    """Paired comparison of two Opik experiments; GateRefusal if it would not be a fair one."""
    require_comparable(candidate, current)
    try:
        result = paired(item_scores(candidate, score_name), item_scores(current, score_name))
    except ValueError as exc:
        raise GateRefusal(f"{candidate.name} and {current.name}: {exc}.") from exc
    total = result.n + result.dropped
    # WHY: an aborted run that is the newest of its name would otherwise decide on a few items.
    if result.n * MIN_COVERAGE[1] < total * MIN_COVERAGE[0]:
        raise GateRefusal(
            f"{candidate.name} and {current.name} were both scored on only {result.n} of {total} "
            "dataset items. Re-run the incomplete experiment before comparing them."
        )
    return result


def gate_notes(
    decision: Decision, candidate: str, current: str, delta: float, applied: bool = True
) -> tuple[str, str]:
    """The `opik_gate` value for the candidate's and for the current version's training experiment."""
    # WHY: the note must not say "promote" when the registry did not take the status change.
    outcome = decision if applied else f"{decision} (not applied)"
    return (
        f"{outcome} vs {current}, delta={delta:+.3f}",
        f"candidate {candidate}: {outcome}, delta={delta:+.3f}",
    )


def require_current_in_production(model: Any, current: str) -> None:
    """GateRefusal unless `current` is the one Production version; a promote demotes only that one."""
    production = model.find_versions(status=STATUS_PRODUCTION)
    if len(production) > 1:
        raise GateRefusal(
            f"several versions are in Production ({', '.join(production)}). "
            "Leave one of them in Production in the Model Registry first."
        )
    if production != [current]:
        raise GateRefusal(
            f"{current} is not the Production version (in Production: {', '.join(production) or 'none'}). "
            "A promote would leave a version in Production that the candidate was never compared "
            "with. Compare against the deployed one: --current production."
        )


def apply_decision(model: Any, candidate: str, current: str, decision: Decision) -> Applied:
    """Write a promote to the registry. Reports what happened and whether it is complete; never raises."""
    if decision != "promote":
        return Applied(done=True, lines=[])
    lines = []
    # WHY: candidate first. If its promotion fails or waits for approval, the current version
    # must stay in Production, so the demotion is not attempted.
    for version, status in ((candidate, STATUS_PRODUCTION), (current, STATUS_STAGING)):
        try:
            model.set_status(version, status)
            actual = model.status(version)
        except Exception as exc:
            lines.append(f"{version}: could not set status {status} ({exc}); nothing else was changed")
            return Applied(done=False, lines=lines)
        if actual != status:
            lines.append(
                f"{version}: requested status {status}, the registry still shows {actual} "
                "(an approval request may be pending); nothing else was changed"
            )
            return Applied(done=False, lines=lines)
        lines.append(f"{version}: status is now {status}")
    return Applied(done=True, lines=lines)


def _load_experiment(client: Any, version: str) -> Any:
    from roadwork_demo.config import experiment_name

    name = experiment_name(GATE_VARIANT, version)
    experiment = find_experiment(client, name)
    if experiment is None:
        raise SystemExit(
            f"Opik experiment not found: {name}. Run "
            f"scripts/05_run_experiments.py --detector {version} --variants {GATE_VARIANT} first."
        )
    return experiment


def main() -> None:
    ap = argparse.ArgumentParser(description="Promote or hold a registered detector version.")
    ap.add_argument("--candidate", required=True, help="registry version to evaluate, e.g. 2.0.0")
    ap.add_argument("--current", default=PRODUCTION, help="version to beat (default: the Production one)")
    ap.add_argument("--min-delta", type=float, default=0.03, help="smallest accuracy gain that promotes")
    ap.add_argument("--apply", action="store_true", help="write the decision to Comet")
    args = ap.parse_args()

    import opik

    from roadwork_demo.config import STOCK_VERSION, exit_if_dry_run, get_settings
    from roadwork_demo.pipeline import handoff_or_exit

    s = get_settings()
    exit_if_dry_run(s, f"compare detector_vlm-{args.candidate} with the {args.current} version")
    if STOCK_VERSION in (args.candidate, args.current):
        raise SystemExit("The gate compares registered versions; the stock baseline is a reference only.")
    candidate, current = handoff_or_exit(args.candidate), handoff_or_exit(args.current)
    if candidate.model_version == current.model_version:
        raise SystemExit(f"{candidate.model_version} is already the current version; nothing to compare.")

    client = opik.Opik()
    try:
        result = compare(
            _load_experiment(client, candidate.model_version), _load_experiment(client, current.model_version)
        )
    except GateRefusal as exc:
        raise SystemExit(f"Refusing to compare: {exc}") from exc
    decision = decide(result.delta, args.min_delta)

    print(f"candidate {s.registry_model}:{candidate.model_version}  accuracy {result.mean_candidate:.3f}")
    print(f"current   {s.registry_model}:{current.model_version}  accuracy {result.mean_current:.3f}")
    print(f"items compared: {result.n} (dropped, not scored in both: {result.dropped})")
    print(f"delta: {result.delta:+.3f} (min delta {args.min_delta})")
    print(
        f"items won / lost by the candidate: {result.wins} / {result.losses}, "
        f"two-sided sign test p = {result.p_value:.3f} (context, not a threshold)"
    )
    print(f"decision: {decision}")

    if not args.apply:
        print("dry run: nothing written")
        return

    from comet_ml import API

    api = API()
    model = api.get_model(s.workspace, s.registry_model)
    if decision == "promote":
        try:
            require_current_in_production(model, current.model_version)
        except GateRefusal as exc:
            raise SystemExit(f"Refusing to apply: {exc} Nothing was written.") from exc
    applied = apply_decision(model, candidate.model_version, current.model_version, decision)
    for line in applied.lines:
        print(line)
    notes = gate_notes(
        decision, candidate.model_version, current.model_version, result.delta, applied=applied.done
    )
    for handoff, note in zip((candidate, current), notes, strict=True):
        experiment = api.get_experiment_by_key(handoff.experiment_key)
        if experiment is None:
            print(f"{handoff.model_version}: training experiment {handoff.experiment_key} not found")
            continue
        experiment.log_other("opik_gate", note)
        print(f"{handoff.model_version}: opik_gate = '{note}' on {handoff.experiment_url}")
    if not applied.done:
        raise SystemExit("The promote did not reach the Model Registry in full; check the statuses there.")


if __name__ == "__main__":
    main()
