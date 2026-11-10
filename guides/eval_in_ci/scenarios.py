"""Driving-scenario dataset, production requests, plan parsing and the sub-metrics."""

# WHY: every target value is stated in the input, so a perfect prompt can reach 100%; eight items use
# maneuvers that prompts/strong.txt does not list, which is the headroom the optimizer can find.

import json
from typing import Any

from opik.evaluation.metrics import BaseMetric, score_result

from composite_metric import CompositePassMetric


def _scenario(sid: str, text: str, actor: str, maneuver: str, speed: int, gap: int) -> dict[str, Any]:
    return {
        "scenario_id": sid,
        "input": text,
        "expected": {
            "actors": ["ego", actor],
            "maneuver": maneuver,
            "parameters": {"speed_mps": speed, "gap_m": gap},
        },
    }


SCENARIOS: list[dict[str, Any]] = [
    _scenario("s01", "Ego car follows a lead car at 20 m/s with a 30 m gap.", "car", "follow", 20, 30),
    _scenario(
        "s02",
        "Ego car changes to the left lane at 25 m/s to pass a slow truck 15 m ahead.",
        "truck",
        "lane_change_left",
        25,
        15,
    ),
    _scenario(
        "s03",
        "Ego car brakes at 12 m/s for a pedestrian crossing 40 m ahead.",
        "pedestrian",
        "brake",
        12,
        40,
    ),
    _scenario(
        "s04",
        "Ego car overtakes a cyclist on a straight road at 15 m/s, 10 m behind it.",
        "cyclist",
        "overtake",
        15,
        10,
    ),
    _scenario("s05", "Ego car merges onto a highway at 28 m/s, 25 m behind a van.", "van", "merge", 28, 25),
    _scenario("s06", "Ego car at 5 m/s stops at a red light with a bus 8 m ahead.", "bus", "stop", 5, 8),
    _scenario(
        "s07",
        "Ego car changes to the right lane at 22 m/s beside a motorcycle 12 m ahead.",
        "motorcycle",
        "lane_change_right",
        22,
        12,
    ),
    _scenario("s08", "Ego car follows a delivery van at 18 m/s with a 35 m gap.", "van", "follow", 18, 35),
    _scenario(
        "s09",
        "Ego car overtakes a tractor on a rural road at 17 m/s, 14 m behind it.",
        "tractor",
        "overtake",
        17,
        14,
    ),
    _scenario("s10", "Ego car brakes at 14 m/s for a deer standing 45 m ahead.", "deer", "brake", 14, 45),
    _scenario(
        "s11",
        "Ego car merges into city traffic at 11 m/s, 9 m behind a taxi.",
        "taxi",
        "merge",
        11,
        9,
    ),
    _scenario(
        "s12",
        "Ego car at 3 m/s stops behind a garbage truck that halted 6 m ahead.",
        "truck",
        "stop",
        3,
        6,
    ),
    _scenario(
        "s13",
        "Ego car brakes hard in an emergency at 30 m/s for a stalled car 50 m ahead.",
        "car",
        "emergency_brake",
        30,
        50,
    ),
    _scenario(
        "s14",
        "Ego car makes an emergency stop at 24 m/s when a child runs out 18 m ahead.",
        "child",
        "emergency_brake",
        24,
        18,
    ),
    _scenario(
        "s15",
        "Ego car yields at 8 m/s to an oncoming car 20 m away at an intersection.",
        "car",
        "yield",
        8,
        20,
    ),
    _scenario(
        "s16",
        "Ego car yields at 7 m/s to an ambulance approaching 35 m behind it.",
        "ambulance",
        "yield",
        7,
        35,
    ),
    _scenario(
        "s17",
        "Ego car turns left at a junction at 6 m/s as a scooter passes 9 m away.",
        "scooter",
        "turn_left",
        6,
        9,
    ),
    _scenario(
        "s18",
        "Ego car turns right at 5 m/s while a cyclist waits 7 m away at the corner.",
        "cyclist",
        "turn_right",
        5,
        7,
    ),
    _scenario(
        "s19",
        "Ego car makes a U-turn at 4 m/s with a parked bus 11 m ahead.",
        "bus",
        "u_turn",
        4,
        11,
    ),
    _scenario(
        "s20",
        "Ego car makes a U-turn on an empty road at 2 m/s, 16 m from a jogger.",
        "jogger",
        "u_turn",
        2,
        16,
    ),
]

# WHY: requests the app answers after promotion; none is a dataset item, so Logs shows unseen traffic.
PRODUCTION_REQUESTS: list[str] = [
    "Ego car follows a pickup truck at 19 m/s with a 28 m gap.",
    "Ego car brakes at 10 m/s for a dog crossing 22 m ahead.",
    "Ego car yields at 9 m/s to a fire truck 40 m behind it.",
    "Ego car turns left at 7 m/s while a bus waits 13 m away.",
    "Ego car changes to the left lane at 27 m/s to pass a trailer 21 m ahead.",
    "Ego car makes a U-turn at 3 m/s with a parked van 12 m ahead.",
]


# WHY: taking the outermost braces also skips code fences and any prose around the JSON.
def parse_plan(text: str) -> dict[str, Any]:
    """Extract the JSON object from model text; return {} when there is none."""
    stripped = text or ""
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(stripped[start : end + 1])
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _binary(name: str, ok: bool, reason: str) -> score_result.ScoreResult:
    return score_result.ScoreResult(name=name, value=1.0 if ok else 0.0, reason=reason)


class ActorsCorrect(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="actors_correct", track=False)

    def score(self, expected: dict, output: dict, **_: Any) -> score_result.ScoreResult:
        actors = output.get("actors")
        if not isinstance(actors, list) or not all(isinstance(a, str) for a in actors):
            return _binary(self.name, False, "missing actors")
        return _binary(self.name, sorted(actors) == sorted(expected["actors"]), f"actors {actors}")


class ManeuverCorrect(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="maneuver_correct", track=False)

    def score(self, expected: dict, output: dict, **_: Any) -> score_result.ScoreResult:
        maneuver = output.get("maneuver")
        if maneuver is None:
            return _binary(self.name, False, "missing maneuver")
        ok = maneuver == expected["maneuver"]
        return _binary(self.name, ok, f"maneuver {maneuver} vs {expected['maneuver']}")


class ParametersCorrect(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="parameters_correct", track=False)

    def score(self, expected: dict, output: dict, **_: Any) -> score_result.ScoreResult:
        parameters = output.get("parameters")
        if parameters is None:
            return _binary(self.name, False, "missing parameters")
        return _binary(self.name, parameters == expected["parameters"], f"parameters {parameters}")


# WHY: track=True keeps the composite span on experiment traces; the optimizer and tests pass track=False.
def build_metric(track: bool = True) -> CompositePassMetric:
    return CompositePassMetric(
        metrics=[ActorsCorrect(), ManeuverCorrect(), ParametersCorrect()],
        thresholds={
            "actors_correct": 1.0,
            "maneuver_correct": 1.0,
            "parameters_correct": 1.0,
        },
        track=track,
    )
