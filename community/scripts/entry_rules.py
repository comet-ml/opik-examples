from __future__ import annotations

import re
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


def _section_bodies(markdown: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            if current is not None:
                bodies[current] = "\n".join(buffer).strip()
            current = heading.group(1).strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        bodies[current] = "\n".join(buffer).strip()
    return bodies


def _looks_like_placeholder(body: str) -> bool:
    lowered = body.lower()
    return body == "" or any(token.lower() in lowered for token in PLACEHOLDER_TOKENS)


def validate_readme(entry: Path) -> list[str]:
    readme_path = entry / "README.md"
    if not readme_path.is_file():
        return [f"{entry.name}: missing README.md"]

    bodies = _section_bodies(readme_path.read_text())
    errors: list[str] = []
    for section in REQUIRED_SECTIONS:
        if section not in bodies:
            errors.append(f"{entry.name}: README.md missing required section '## {section}'")
        elif _looks_like_placeholder(bodies[section]):
            errors.append(
                f"{entry.name}: README.md section '## {section}' is empty or still a placeholder"
            )
    return errors


def validate_proof(entry: Path) -> list[str]:
    errors: list[str] = []
    if not (entry / "opik-proof.png").is_file():
        errors.append(f"{entry.name}: missing opik-proof.png (screenshot of your Opik traces)")
        return errors
    readme_path = entry / "README.md"
    text = readme_path.read_text() if readme_path.is_file() else ""
    if "opik-proof.png" not in text:
        errors.append(f"{entry.name}: opik-proof.png must be referenced from README.md")
    return errors
