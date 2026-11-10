"""Job summary, step outputs and failure handling shared by the evaluate and optimize steps."""

import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opik_access import ConfigError


def append_text(path: Path | None, text: str) -> None:
    """Append to a file such as $GITHUB_STEP_SUMMARY; do nothing without a path."""
    if path:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(text.rstrip("\n") + "\n")


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_github_output(path: Path | None, values: dict[str, str]) -> None:
    """Append key=value lines to $GITHUB_OUTPUT."""
    append_text(path, "\n".join(f"{key}={value}" for key, value in values.items()))


# WHY: one place turns any failure into exit code 2 plus a job-summary entry, so the run page says
# what broke and what state it left behind instead of only showing red.
def run_step(step: Callable[[], int], *, title: str, summary: Path | None, outcome: Callable[[], str]) -> int:
    """Run a step; on error print it, add it to the summary with the outcome line, and return 2."""
    try:
        return step()
    except (ConfigError, ValueError, OSError) as exc:
        message = str(exc)
    except Exception as exc:
        traceback.print_exc()
        message = f"{type(exc).__name__}: {exc}"
    print(message, file=sys.stderr)
    append_text(summary, f"## {title}\n\nFailed: {message}\n\n{outcome()}")
    return 2
