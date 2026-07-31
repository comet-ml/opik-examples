"""Resolve dotted trace field-paths into the kwargs a metric's score() expects.

A `variables` mapping looks like {"input": "input.question", "output": "output.answer"}:
each key is a metric score() parameter, each value a dotted path into the trace's
top-level dicts (`input`, `output`, `metadata`). This is the Opik "variable mapping".
"""

from typing import Any


class MissingField(Exception):
    """A variable's dotted path could not be resolved against a trace."""


def resolve_path(trace_data: dict[str, Any], path: str) -> Any:
    """Read `path` (e.g. "output.context") out of trace_data.

    First segment selects a top-level key (input/output/metadata); remaining
    segments index into nested dicts. List/scalar leaf values are returned as-is.
    Raises MissingField if any segment is absent or a non-dict is indexed.
    """
    segments = path.split(".")
    current: Any = trace_data
    traversed: list[str] = []
    for segment in segments:
        if not isinstance(current, dict) or segment not in current:
            where = ".".join(traversed) or "<root>"
            raise MissingField(f"cannot resolve '{path}': '{segment}' missing under '{where}'")
        current = current[segment]
        traversed.append(segment)
    return current


def resolve_variables(trace_data: dict[str, Any], variables: dict[str, str]) -> dict[str, Any]:
    """Map {param: dotted_path} to {param: resolved_value}. Propagates MissingField."""
    return {param: resolve_path(trace_data, path) for param, path in variables.items()}
