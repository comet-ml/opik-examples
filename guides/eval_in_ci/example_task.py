"""Deterministic toy driving-scenario task, sub-metrics and dataset."""

import os
from typing import Any

import opik
from opik.evaluation.metrics import BaseMetric, score_result

from composite_metric import CompositePassMetric

DATASET_NAME = "eval-in-ci-example"
PROJECT_NAME = "eval-in-ci-example"

SCENARIOS: list[dict[str, Any]] = [
    {
        "scenario_id": "s01",
        "input": "Ego car follows a lead car at 20 m/s with a 30 m gap.",
        "expected": {
            "actors": ["ego", "lead_car"],
            "maneuver": "follow",
            "parameters": {"speed_mps": 20, "gap_m": 30},
        },
    },
    {
        "scenario_id": "s02",
        "input": "Ego car changes to the left lane at 25 m/s past a slow truck.",
        "expected": {
            "actors": ["ego", "truck"],
            "maneuver": "lane_change_left",
            "parameters": {"speed_mps": 25, "gap_m": 15},
        },
    },
    {
        "scenario_id": "s03",
        "input": "Ego car brakes for a pedestrian crossing 40 m ahead at 12 m/s.",
        "expected": {
            "actors": ["ego", "pedestrian"],
            "maneuver": "brake",
            "parameters": {"speed_mps": 12, "gap_m": 40},
        },
    },
    {
        "scenario_id": "s04",
        "input": "Ego car overtakes a cyclist on a straight road at 15 m/s.",
        "expected": {
            "actors": ["ego", "cyclist"],
            "maneuver": "overtake",
            "parameters": {"speed_mps": 15, "gap_m": 10},
        },
    },
    {
        "scenario_id": "s05",
        "input": "Ego car merges onto a highway at 28 m/s behind a van.",
        "expected": {
            "actors": ["ego", "van"],
            "maneuver": "merge",
            "parameters": {"speed_mps": 28, "gap_m": 25},
        },
    },
    {
        "scenario_id": "s06",
        "input": "Ego car stops at a red light with a bus waiting 8 m ahead.",
        "expected": {
            "actors": ["ego", "bus"],
            "maneuver": "stop",
            "parameters": {"speed_mps": 0, "gap_m": 8},
        },
    },
    {
        "scenario_id": "s07",
        "input": "Ego car yields to an oncoming car at an intersection at 8 m/s.",
        "expected": {
            "actors": ["ego", "oncoming_car"],
            "maneuver": "yield",
            "parameters": {"speed_mps": 8, "gap_m": 20},
        },
    },
    {
        "scenario_id": "s08",
        "input": "Ego car changes to the right lane at 22 m/s beside a motorcycle.",
        "expected": {
            "actors": ["ego", "motorcycle"],
            "maneuver": "lane_change_right",
            "parameters": {"speed_mps": 22, "gap_m": 12},
        },
    },
    {
        "scenario_id": "s09",
        "input": "Ego car follows a delivery van at 18 m/s with a 35 m gap.",
        "expected": {
            "actors": ["ego", "van"],
            "maneuver": "follow",
            "parameters": {"speed_mps": 18, "gap_m": 35},
        },
    },
    {
        "scenario_id": "s10",
        "input": "Ego car turns left at a junction at 6 m/s as a scooter passes.",
        "expected": {
            "actors": ["ego", "scooter"],
            "maneuver": "turn_left",
            "parameters": {"speed_mps": 6, "gap_m": 9},
        },
    },
    {
        "scenario_id": "s11",
        "input": "Ego car brakes hard for a stalled car 50 m ahead at 30 m/s.",
        "expected": {
            "actors": ["ego", "stalled_car"],
            "maneuver": "emergency_brake",
            "parameters": {"speed_mps": 30, "gap_m": 50},
        },
    },
    {
        "scenario_id": "s12",
        "input": "Ego car overtakes a tractor on a rural road at 17 m/s.",
        "expected": {
            "actors": ["ego", "tractor"],
            "maneuver": "overtake",
            "parameters": {"speed_mps": 17, "gap_m": 14},
        },
    },
]

V1_BROKEN = frozenset({"s03", "s07", "s11"})
V2_FIXED = frozenset({"s03", "s07"})
V2_NEWLY_BROKEN = frozenset({"s05"})

_BY_ID: dict[str, dict[str, Any]] = {s["scenario_id"]: s["expected"] for s in SCENARIOS}


def _broken_ids(version: str) -> frozenset[str]:
    if version == "v2":
        return (V1_BROKEN - V2_FIXED) | V2_NEWLY_BROKEN
    return V1_BROKEN


def scenario_agent(scenario_id: str, input: str, version: str | None = None, **_: Any) -> dict[str, Any]:
    """Return the expected plan, with the maneuver wrong for "broken" scenarios."""
    # WHY: an explicit version lets the offline demo run v1 and v2 without touching the environment.
    version = version or os.environ.get("AGENT_VERSION", "v1")
    plan = dict(_BY_ID[scenario_id])
    if scenario_id in _broken_ids(version):
        plan["maneuver"] = "unknown"
    return {"output": plan}


def _binary(name: str, ok: bool, reason: str) -> score_result.ScoreResult:
    return score_result.ScoreResult(name=name, value=1.0 if ok else 0.0, reason=reason)


class ActorsCorrect(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="actors_correct", track=False)

    def score(self, expected: dict, output: dict, **_: Any) -> score_result.ScoreResult:
        ok = sorted(output["actors"]) == sorted(expected["actors"])
        return _binary(self.name, ok, f"actors {output['actors']}")


class ManeuverCorrect(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="maneuver_correct", track=False)

    def score(self, expected: dict, output: dict, **_: Any) -> score_result.ScoreResult:
        ok = output["maneuver"] == expected["maneuver"]
        return _binary(self.name, ok, f"maneuver {output['maneuver']} vs {expected['maneuver']}")


class ParametersCorrect(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="parameters_correct", track=False)

    def score(self, expected: dict, output: dict, **_: Any) -> score_result.ScoreResult:
        ok = output["parameters"] == expected["parameters"]
        return _binary(self.name, ok, f"parameters {output['parameters']}")


def build_metric() -> CompositePassMetric:
    # WHY: track=False keeps direct score() calls from opening Opik traces (and from needing credentials).
    return CompositePassMetric(
        metrics=[ActorsCorrect(), ManeuverCorrect(), ParametersCorrect()],
        thresholds={
            "actors_correct": 1.0,
            "maneuver_correct": 1.0,
            "parameters_correct": 1.0,
        },
        track=False,
    )


def ensure_dataset(client: opik.Opik, name: str = DATASET_NAME) -> opik.Dataset:
    """Create the dataset if missing and insert the scenarios (deduped by content)."""
    dataset = client.get_or_create_dataset(
        name=name, description="Toy driving scenarios for the eval-in-CI example"
    )
    dataset.insert(SCENARIOS)
    return dataset


if __name__ == "__main__":
    created = ensure_dataset(opik.Opik())
    print(f"{created.name}: {len(SCENARIOS)} items")
