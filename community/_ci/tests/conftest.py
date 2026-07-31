from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PROJECT = {
    "title": "Real-time support agent with Opik tracing",
    "description": "A support agent traced end-to-end with an LLM-judge eval loop.",
    "author": "jane-doe",
    "repo": "https://github.com/jane-doe/support-agent",
}


def make_project(**overrides: object) -> dict:
    """Return a valid project dict, with fields overridden or (if None) removed."""
    project = dict(DEFAULT_PROJECT)
    for key, value in overrides.items():
        if value is None:
            project.pop(key, None)
        else:
            project[key] = value
    return project


def write_projects(base: Path, projects: list | None = None, *, raw: str | None = None) -> Path:
    """Write a projects.yaml into `base` and return its path.

    Pass `raw` to write arbitrary file contents (e.g. invalid YAML).
    """
    path = base / "projects.yaml"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    else:
        items = [make_project()] if projects is None else projects
        path.write_text(yaml.safe_dump(items, sort_keys=False), encoding="utf-8")
    return path
