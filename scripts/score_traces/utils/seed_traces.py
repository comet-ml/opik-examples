"""Populate a test project with hardcoded Q&A traces (no LLM required).

Run `uv run python utils/seed_traces.py` to create traces you can then score with
`uv run python score_traces.py`. Seeding needs no gateway — only the judge step does.
"""

import os

import opik

PROJECT_NAME = os.environ.get("OPIK_PROJECT_NAME", "score-traces-example")

# ~10 traces, deliberate good/bad mix so evaluation scores show a real spread.
SEED_TRACES = [
    {
        "input": {"question": "What is 2+2?", "expected": "4"},
        "output": {"answer": "4", "context": ["basic arithmetic"]},
    },
    {
        "input": {"question": "Capital of France?", "expected": "Paris"},
        "output": {"answer": "Paris", "context": ["Paris is the capital of France"]},
    },
    {
        "input": {"question": "Who wrote Hamlet?", "expected": "Shakespeare"},
        "output": {"answer": "Shakespeare", "context": ["Hamlet is a play by William Shakespeare"]},
    },
    {
        "input": {"question": "Boiling point of water in C?", "expected": "100"},
        "output": {"answer": "100", "context": ["Water boils at 100C at sea level"]},
    },
    {
        "input": {"question": "Largest planet?", "expected": "Jupiter"},
        "output": {"answer": "Jupiter", "context": ["Jupiter is the largest planet"]},
    },
    # --- deliberately wrong / hallucinated / off-topic ---
    {
        "input": {"question": "What is 2+2?", "expected": "4"},
        "output": {"answer": "5", "context": ["basic arithmetic"]},
    },  # wrong answer
    {
        "input": {"question": "Capital of Japan?", "expected": "Tokyo"},
        "output": {"answer": "Kyoto", "context": ["Tokyo is the capital of Japan"]},
    },  # contradicts context
    {
        "input": {"question": "Speed of light?", "expected": "299792458 m/s"},
        "output": {"answer": "It was a sunny day.", "context": ["physics constants"]},
    },  # off-topic
    {
        "input": {"question": "Chemical symbol for gold?", "expected": "Au"},
        "output": {"answer": "Gd", "context": ["Gold's symbol is Au"]},
    },  # wrong, contradicts context
    {
        "input": {"question": "How many days in a week?", "expected": "7"},
        "output": {"answer": "7", "context": ["A week has seven days"]},
    },
]


def main() -> None:
    dry_run = not (os.environ.get("OPIK_API_KEY") and os.environ.get("OPIK_WORKSPACE"))
    if dry_run:
        print(
            f"DRY_RUN: would seed {len(SEED_TRACES)} traces into project '{PROJECT_NAME}'. "
            "Set OPIK_API_KEY + OPIK_WORKSPACE to seed for real."
        )
        return

    client = opik.Opik(project_name=PROJECT_NAME)
    for item in SEED_TRACES:
        client.trace(
            name="seed-qa",
            project_name=PROJECT_NAME,
            input=item["input"],
            output=item["output"],
        )
    client.flush()
    print(f"Seeded {len(SEED_TRACES)} traces into project '{PROJECT_NAME}'.")


if __name__ == "__main__":
    main()
