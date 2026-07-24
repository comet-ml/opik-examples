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
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
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

    bodies = _section_bodies(readme_path.read_text(encoding="utf-8"))
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
    readme_path = entry / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""

    png_path = entry / "opik-proof.png"
    if png_path.is_file():
        if "opik-proof.png" not in readme_text:
            return [f"{entry.name}: opik-proof.png must be referenced from README.md"]
        return []

    data, _ = load_meta(entry)
    proof_url = data.get("proof_url")
    if _nonempty_str(proof_url) and str(proof_url).startswith("http"):
        return []

    return [
        f"{entry.name}: no proof of Opik usage — commit an opik-proof.png referenced "
        f"from README.md, or set an http(s) 'proof_url' in meta.yaml"
    ]


_FOLDER_NAME_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"""OPIK_API_KEY\s*[=:]\s*["'][^"']+["']"""),
]
_TEXT_SUFFIXES = {".py", ".ipynb", ".md", ".txt", ".yaml", ".yml", ".toml", ".sh", ".json"}
_OPIK_MARKERS = ["import opik", "from opik", "@opik.track", "opik.Opik(", "OPIK_"]


def validate_folder_name(entry: Path) -> list[str]:
    if not _FOLDER_NAME_RE.match(entry.name):
        return [
            f"{entry.name}: folder name must be lowercase '<author>_<project>' "
            f"(letters/digits/underscores, at least one underscore)"
        ]
    return []


def _iter_text_files(entry: Path):
    for path in entry.rglob("*"):
        if path.is_file() and path.suffix.lower() in _TEXT_SUFFIXES:
            yield path


def validate_no_secrets(entry: Path) -> list[str]:
    errors: list[str] = []
    for path in entry.rglob(".env"):
        if path.is_file() and path.name == ".env":
            errors.append(
                f"{entry.name}: committed .env file at {path.relative_to(entry)} — remove it"
            )

    for path in _iter_text_files(entry):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(
                    f"{entry.name}: possible hardcoded secret/key in {path.relative_to(entry)} "
                    f"— load credentials from environment variables instead"
                )
                break
    return errors


def validate_code_uses_opik(entry: Path) -> list[str]:
    data, load_errors = load_meta(entry)
    if load_errors:
        return []  # meta problems are reported by validate_meta; don't double-report
    if data.get("hosted") is not True:
        return []

    for path in entry.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".ipynb"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in _OPIK_MARKERS):
                return []
    return [
        f"{entry.name}: hosted entry has no code that uses Opik "
        f"(expected one of: import opik, @opik.track, opik.Opik(, OPIK_)"
    ]
