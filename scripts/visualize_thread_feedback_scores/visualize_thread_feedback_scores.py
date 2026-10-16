#!/usr/bin/env python3
"""Plot turn-by-turn feedback scores for a multi-turn Opik conversation thread.

Fetches every trace in a thread, reads each trace's feedback scores, and plots how
those scores change turn by turn.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import opik

OPIK_API_KEY = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_URL = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")

DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)

SAMPLE_TURNS: list[dict[str, Any]] = [
    {
        "turn": 1,
        "trace_id": "demo-trace-1",
        "start_time": "2026-01-01T10:00:00+00:00",
        "scores": {"helpfulness": 0.92, "accuracy": 0.88, "toxicity": 0.05},
    },
    {
        "turn": 2,
        "trace_id": "demo-trace-2",
        "start_time": "2026-01-01T10:00:45+00:00",
        "scores": {"helpfulness": 0.81, "accuracy": 0.74, "toxicity": 0.08},
    },
    {
        "turn": 3,
        "trace_id": "demo-trace-3",
        "start_time": "2026-01-01T10:01:20+00:00",
        "scores": {"helpfulness": 0.55, "accuracy": 0.49, "toxicity": 0.22},
    },
    {
        "turn": 4,
        "trace_id": "demo-trace-4",
        "start_time": "2026-01-01T10:02:05+00:00",
        "scores": {"helpfulness": 0.70, "accuracy": 0.66, "toxicity": 0.12},
    },
]


@dataclass(frozen=True)
class TurnScore:
    turn: int
    trace_id: str
    start_time: str
    scores: dict[str, float]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project-name",
        default=os.environ.get("OPIK_PROJECT_NAME", ""),
        help="Opik project that owns the thread (or set OPIK_PROJECT_NAME).",
    )
    parser.add_argument("--thread-id", default="", help="Conversation thread id to visualise.")
    parser.add_argument(
        "--output",
        default="thread_feedback_scores.png",
        help="Path for the PNG chart (default: thread_feedback_scores.png).",
    )
    parser.add_argument(
        "--csv",
        default="",
        help="Optional path to also write a per-turn CSV of score values.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Use sample data; do not call Opik.")
    return parser


def _feedback_scores_to_dict(raw: Any) -> dict[str, float]:
    scores: dict[str, float] = {}
    for item in raw or []:
        name = getattr(item, "name", None)
        if name is None and isinstance(item, dict):
            name = item.get("name")
        value = getattr(item, "value", None)
        if value is None and isinstance(item, dict):
            value = item.get("value")
        if name and value is not None:
            scores[str(name)] = float(value)
    return scores


def _trace_start_time(trace: Any) -> datetime:
    start = getattr(trace, "start_time", None)
    if isinstance(start, datetime):
        return start if start.tzinfo else start.replace(tzinfo=UTC)
    if isinstance(start, str) and start:
        return datetime.fromisoformat(start.replace("Z", "+00:00"))
    return datetime.fromtimestamp(0, tz=UTC)


def traces_to_turn_scores(traces: list[Any]) -> list[TurnScore]:
    ordered = sorted(traces, key=_trace_start_time)
    turns: list[TurnScore] = []
    for index, trace in enumerate(ordered, start=1):
        trace_id = str(getattr(trace, "id", "") or f"turn-{index}")
        start = _trace_start_time(trace).isoformat()
        scores = _feedback_scores_to_dict(getattr(trace, "feedback_scores", None))
        turns.append(TurnScore(turn=index, trace_id=trace_id, start_time=start, scores=scores))
    return turns


def fetch_thread_turn_scores(
    client: opik.Opik,
    *,
    project_name: str,
    thread_id: str,
) -> list[TurnScore]:
    # Opik filter_string needs the thread id quoted as a string literal.
    filter_string = f'thread_id = "{thread_id}"'
    traces = client.search_traces(
        project_name=project_name,
        filter_string=filter_string,
        max_results=1000,
        truncate=True,
    )
    return traces_to_turn_scores(list(traces or []))


def sample_turn_scores() -> list[TurnScore]:
    return [
        TurnScore(
            turn=int(row["turn"]),
            trace_id=str(row["trace_id"]),
            start_time=str(row["start_time"]),
            scores={k: float(v) for k, v in dict(row["scores"]).items()},
        )
        for row in SAMPLE_TURNS
    ]


def write_csv(turns: list[TurnScore], path: Path) -> None:
    score_names = sorted({name for turn in turns for name in turn.scores})
    fieldnames = ["turn", "trace_id", "start_time", *score_names]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for turn in turns:
            row: dict[str, Any] = {
                "turn": turn.turn,
                "trace_id": turn.trace_id,
                "start_time": turn.start_time,
            }
            row.update(turn.scores)
            writer.writerow(row)


def plot_turn_scores(turns: list[TurnScore], output: Path, *, title: str) -> None:
    if not turns:
        raise ValueError("No turns to plot.")

    score_names = sorted({name for turn in turns for name in turn.scores})
    if not score_names:
        raise ValueError("Traces were found, but none have feedback scores to plot.")

    xs = [turn.turn for turn in turns]
    fig, ax = plt.subplots(figsize=(10, 5))
    for name in score_names:
        ys = [turn.scores.get(name) for turn in turns]
        ax.plot(xs, ys, marker="o", linewidth=2, label=name)

    ax.set_xlabel("Turn")
    ax.set_ylabel("Feedback score")
    ax.set_title(title)
    ax.set_xticks(xs)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="best")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def run(
    client: opik.Opik | None,
    *,
    project_name: str,
    thread_id: str,
    output: Path,
    csv_path: Path | None,
    dry_run: bool,
) -> None:
    if dry_run:
        turns = sample_turn_scores()
        title = "DRY RUN — sample multi-turn feedback scores"
        print(f"[DRY RUN] plotting {len(turns)} sample turn(s) -> {output}")
    else:
        if not project_name or not thread_id:
            raise SystemExit("--project-name and --thread-id are required for a live run.")
        if client is None:
            raise SystemExit("Opik client is required for a live run.")
        print(f"Fetching traces for thread '{thread_id}' in project '{project_name}' via {OPIK_URL}...")
        turns = fetch_thread_turn_scores(client, project_name=project_name, thread_id=thread_id)
        if not turns:
            raise SystemExit(f"No traces found for thread_id={thread_id!r} in project={project_name!r}.")
        title = f"Thread {thread_id} — feedback scores by turn"
        print(f"Found {len(turns)} turn(s).")

    plot_turn_scores(turns, output, title=title)
    print(f"Wrote chart: {output.resolve()}")

    if csv_path is not None:
        write_csv(turns, csv_path)
        print(f"Wrote CSV:   {csv_path.resolve()}")

    for turn in turns:
        score_text = ", ".join(f"{k}={v:.3f}" for k, v in sorted(turn.scores.items())) or "(no scores)"
        print(f"  turn {turn.turn}: {score_text}")


def main() -> int:
    args = build_parser().parse_args()
    dry_run = DRY_RUN or args.dry_run
    output = Path(args.output)
    csv_path = Path(args.csv) if args.csv else None

    if dry_run:
        if not args.dry_run:
            print("OPIK_API_KEY / OPIK_WORKSPACE not set — running in DRY_RUN.", file=sys.stderr)
        run(
            None,
            project_name=args.project_name,
            thread_id=args.thread_id,
            output=output,
            csv_path=csv_path,
            dry_run=True,
        )
        return 0

    client = opik.Opik()
    run(
        client,
        project_name=args.project_name,
        thread_id=args.thread_id,
        output=output,
        csv_path=csv_path,
        dry_run=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
