from __future__ import annotations

from pathlib import Path

import yaml

REQUIRED_SECTIONS = [
    "What I built",
    "Problem it solves",
    "What I learned",
    "How I used Opik",
]
PLACEHOLDER_TOKENS = ["TODO", "FILL ME IN", "<!-- replace"]
VALID_PLATFORMS = {"cloud", "self-hosted"}

_REQUIRED_STRING_FIELDS = ["title", "description", "author"]


def load_meta(entry: Path) -> tuple[dict, list[str]]:
    meta_path = entry / "meta.yaml"
    if not meta_path.is_file():
        return {}, [f"{entry.name}: missing meta.yaml"]
    try:
        data = yaml.safe_load(meta_path.read_text())
    except yaml.YAMLError as exc:
        return {}, [f"{entry.name}: meta.yaml is not valid YAML ({exc})"]
    if not isinstance(data, dict):
        return {}, [f"{entry.name}: meta.yaml must be a mapping"]
    return data, []


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate_meta(entry: Path) -> list[str]:
    data, errors = load_meta(entry)
    if errors:
        return errors

    name = entry.name

    for field in _REQUIRED_STRING_FIELDS:
        if not _nonempty_str(data.get(field)):
            errors.append(
                f"{name}: meta.yaml field '{field}' is required and must be a non-empty string"
            )

    links = data.get("links")
    if not isinstance(links, dict) or not any(
        _nonempty_str(v) and str(v).startswith("http") for v in links.values()
    ):
        errors.append(f"{name}: meta.yaml 'links' must contain at least one http(s) link")

    platform = data.get("opik_platform")
    if platform not in VALID_PLATFORMS:
        errors.append(f"{name}: meta.yaml 'opik_platform' must be one of {sorted(VALID_PLATFORMS)}")

    if not isinstance(data.get("tags"), list):
        errors.append(f"{name}: meta.yaml 'tags' must be a list (may be empty)")

    if not isinstance(data.get("hosted"), bool):
        errors.append(f"{name}: meta.yaml 'hosted' must be a boolean (true/false)")

    return errors
